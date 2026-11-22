# -*- coding: utf-8 -*-
"""OKF-kontraktet på user_mail_ai.mail — mail blir kunskap i minnet.

VARFÖR: mail är den största kunskapskällan i systemet och den enda som
aldrig nådde minnet. Session 24112 ("vad är menyn på torsdag kväll?")
misslyckades trots att agenten hade både `okf_search` och `graph_query` —
svaret låg i ett IMAP-mail som ingen modell indexerade.

DEN GAMLA VÄGEN (avvecklad): `_ingest_message()` anropade
`ai.okf.concept.create_from_mail()` synkront i ingest. Det bröt mot
`okf-indexable-mixin`s krav att inget AI-arbete sker i `create()` — den
embeddar synkront, saknar versionering, brusfilter och dirty-flagga.
Nu sätter ingest bara `okf_dirty`; `cron_okf_index_dirty` arkiverar via
mixinen (samma väg som allt annat).

Källor (se `_okf_body_source`):
    subject      — ämnet
    from_name    — avsändarens namn
    from_email   — avsändarens adress
    received_at  — datum
    .eml-bilagan — brödtexten (via `_get_body_text()`)

Nyckel: `mail:<message_id>` — RFC Message-ID är globalt unikt och ändras
aldrig, exakt vad `okf-indexable-mixin` kräver. Samma brev pollat två
gånger blir en ny version, inte två koncept. Ägarläget `,user.<uid>` läggs
på av mixinen (brevlådan är privat per användare).
"""

import logging

from odoo import models

_logger = logging.getLogger(__name__)

#: Mappar som är brus: skräp, papperskorg, utkast. Aldrig kunskap.
_OKF_SKIP_FOLDERS = frozenset((
    'Junk', 'Junk E-mail', 'Trash', 'Deleted Items', 'Drafts',
))

#: Statusvärden som betyder "medvetet avförd" — indexera aldrig.
_OKF_SKIP_STATUSES = frozenset(('ignored',))

#: Statusvärden som betyder "redo att indexeras". Oklassificerade mail
#: (`new`) BEHÅLLER flaggan och indexeras efter klassificering — annars
#: hinner brusfiltret aldrig se triage-kategorin (design.md D5-risk).
_OKF_READY_STATUSES = frozenset(('classified', 'processed'))


class UserMailAiMailOkf(models.Model):
    _inherit = 'user_mail_ai.mail'

    # ==================================================================
    # Källor — vad mixinen läser
    # ==================================================================

    def _okf_body_source(self):
        """Mailets text: ämne, avsändare, datum och brödtext.

        ÖVERRIDEN — den generiska defaulten (HTML/Text + `name`) passar
        inte: modellen har ingen `name`, och fyra av sex Text-fält är
        JSON-brus (matched_rules, interest_components, attachments_info,
        object_link_candidate). Brödtexten bor i den råa `.eml`-bilagan,
        som defaulten aldrig skulle läsa.
        """
        self.ensure_one()
        parts = []
        if self.subject:
            parts.append('Ämne: %s' % self.subject)
        sender = self.from_name or ''
        if self.from_email:
            sender = ('%s <%s>' % (sender, self.from_email)).strip() \
                if sender else self.from_email
        if sender:
            parts.append('Från: %s' % sender)
        if self.received_at:
            parts.append('Datum: %s' % self.received_at)
        if self.category:
            parts.append('Kategori: %s' % self.category)
        body = self._get_body_text()
        if body:
            parts.append(body)
        return '\n\n'.join(parts)

    def _okf_summary_source(self, owner_vals=None):
        """DETERMINISTISK sammanfattning — ingen LLM.

        Varför: 20–100 mail/dag. En LLM-tur per mail är dyrt och varierar
        mellan körningar; en deterministisk sammanfattning är bättre (samma
        mönster som crm.lead). Ämne + avsändare + datum + triage-kategori
        räcker för att veta vad mailet är.
        """
        self.ensure_one()
        bits = []
        if self.subject:
            bits.append(self.subject)
        if self.from_email or self.from_name:
            bits.append('från %s' % (self.from_email or self.from_name))
        if self.received_at:
            bits.append('(%s)' % self.received_at)
        if self.category:
            bits.append('[%s]' % self.category)
        return ' '.join(bits) or None

    # ==================================================================
    # Kontraktet — vad mixinen frågar om
    # ==================================================================

    def _okf_source_date(self):
        """Mailets KÄLDDATUM: när det togs emot (okf-temporal-recall 7.1).

        Inte när det indexerades. Ett mail från i fjol som pollas i dag är
        inte "nytt" — och med `create_date` som axel hade det sett ut som
        det. `received_at` sätts av IMAP-pollern och ändras aldrig.

        Fallback: `raw_message_id.create_date` (när Odoo först såg mailet)
        och sist `create_date`. En post utan något datum alls lämnas tom —
        den deltar då i sökningen utan tidsvikt, precis som förut.
        """
        self.ensure_one()
        when = self.received_at
        if not when and self.raw_message_id:
            when = self.raw_message_id.create_date
        if not when:
            when = self.create_date
        return when, 'received'

    def _okf_dirty_fields(self):
        """Fält vars ändring gör OKF-fälten inaktuella.

        Bara innehålls- och triagefält. INTE `message_id` (immutabel
        identitet), INTE `folder`/`source_uid` (pollerns bokföring), och
        INTE `memory_state`/`memory_synced_at` (skrivs av minnessynken →
        skulle självåtertända flaggan).

        `received_at` INGÅR (okf-temporal-recall 3.4): källdatumet är en
        del av konceptets mening, och en rättad ankomstitid ska slå igenom
        vid nästa indexering. `partner_id` ingår av samma skäl — det är
        den som bär länken till kunden.
        """
        return {'subject', 'from_email', 'from_name', 'category',
                'status', 'notes', 'received_at', 'partner_id'}

    def _okf_concept_key(self, lang=None, owner_id=None):
        """`mail:<message_id>` — RFC Message-ID, stabilt över tid.

        Identisk med den gamla vägens nyckel (`'mail:%s' % source_ref` där
        `source_ref=message_id`), så ett mail som arkiverats av
        `create_from_mail()` hittas som samma kedja — ingen dubblett.
        """
        self.ensure_one()
        base = 'mail:%s' % (self.message_id or 'id:%s' % self.id)
        if owner_id:
            base = '%s,%s' % (base, owner_id)
        if lang:
            base = '%s,%s' % (base, lang)
        return base

    def _okf_owner_vals(self):
        """Brevlådan är privat — konceptet ägs av användaren."""
        self.ensure_one()
        return {'owner_user_id': self.user_id.id}

    def _okf_artifact_type(self):
        """Bryggans egen typ — spårbar till user_mail_ai i taxonomin."""
        return 'mail'

    def _okf_skip_reason(self):
        """Brusfiltret — tre utfall, se `okf-indexable-mixin`.

        Returnerar en sträng = "medvetet avförd" (flaggan rensas, posten
        indexeras aldrig). Returnerar None = indexera (eller behåll
        flaggan om status ännu inte är klassificerad).

        Ordningen spelar roll: brusmappar och avfärdade mail avförs först,
        sedan hålls oklassificerade tillbaka (behåll flaggan), sist släpps
        de igenom.
        """
        self.ensure_one()
        folder = (self.folder or self.source_folder or '').strip()
        if folder in _OKF_SKIP_FOLDERS:
            return 'mapp %s är brus' % folder
        if self.status in _OKF_SKIP_STATUSES:
            return 'status ignored'
        if self.category == 'newsletter':
            return 'nyhetsbrev'
        if self.status not in _OKF_READY_STATUSES:
            # Oklassificerat — BEHÅLL flaggan. Returnera None så att
            # indexeraren försöker igen efter klassificering. (En tom
            # kropp hade också behållit flaggan, men vi är explicita.)
            return None
        if not self._get_body_text().strip() and not self.subject:
            return 'tomt mail'
        return None

    # ==================================================================
    # .eml-bilagan — bevaras genom versioneringen
    # ==================================================================

    def _okf_eml_attachment(self):
        """Den råa källposten (.eml) som ir.attachment för detta mail.

        Pollern lägger redan en `.eml` på mailet (behövs för triage).
        Denna hjälpare hittar den; den skapas INTE här (ingen filoperation
        i create-vägen — design.md D7).
        """
        self.ensure_one()
        return self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'user_mail_ai.mail'),
            ('res_id', '=', self.id),
            ('mimetype', '=', 'message/rfc822'),
        ], limit=1)

    def _okf_attach_eml_to_concept(self, concept):
        """Koppla mailets `.eml` till konceptet (följer versioneringen).

        Idempotent: skapar bara bilagan om konceptet saknar en
        `message/rfc822`-bilaga. Saknas källposten (t.ex. ett mail utan
        rå .eml) hoppar vi över utan att fela — sökbarheten påverkas inte,
        bara fullständigheten (design.md D7, öppen fråga).
        """
        self.ensure_one()
        if not concept:
            return
        existing = self.env['ir.attachment'].sudo().search_count([
            ('res_model', '=', 'ai.okf.concept'),
            ('res_id', '=', concept.id),
            ('mimetype', '=', 'message/rfc822'),
        ])
        if existing:
            return
        eml = self._okf_eml_attachment()
        if not eml or not eml.datas:
            return
        self.env['ir.attachment'].sudo().create({
            'name': (self.subject or 'email')[:120] + '.eml',
            'datas': eml.datas,
            'mimetype': 'message/rfc822',
            'res_model': 'ai.okf.concept',
            'res_id': concept.id,
        })

    def _okf_links_extra(self):
        """Länkar som relationsfälten inte bär (okf-temporal-recall 7.2).

        `partner_id` och `calendar_event_id` plockas automatiskt av
        mixinens generiska `_okf_links_source()` — de är many2one mot
        modeller som bär mixinen. Det som INTE fångas är:

          `object_model`/`object_res_id`
              Triage kopplar mailet till ett affärsobjekt (crm.lead,
              project.task, helpdesk.ticket …) som en sträng + ett id.
              Utan den här raden blir kopplingen aldrig en länk, och
              frågan "vilka mail hör till det här projektet?" kan inte
              besvaras.

          avsändaradressen
              Ett mail från en kund vi känner igen ska länka till kunden
              även när triage ännu inte satt `partner_id`. Vi SLÅR UPP
              adressen — vi SKAPAR aldrig en kontakt här (indexeringen
              speglar källan; en okänd avsändare blir ingen kontakt).

        Formen är mixinens typade post: ref, kind, date, basis.
        """
        self.ensure_one()
        entries = []

        # 1. Affärsobjektet från triage.
        model = (self.object_model or '').strip()
        if model and self.object_res_id and model in self.env:
            entries.append({
                'ref': '%s,%s' % (model, self.object_res_id),
                'kind': model.replace('.', '_'),
                'date': None,
                'basis': 'explicit',
            })

        # 2. Avsändaren → kund.
        #
        # `partner_id` sätts REDAN vid ingest av `_resolve_partner()`, som
        # hittar eller SKAPAR kontakten. Mixinens generiska
        # `_okf_links_source()` fångar därför den länken automatiskt — vi
        # lägger ingen andra.
        #
        # Fallbacken nedan finns för poster som skapats före `partner_id`
        # fanns (eller där ingest hoppats över): vi SLÅR UPP adressen, vi
        # skapar aldrig en kontakt här. Indexeringen speglar källan.
        if not self.partner_id and self.from_email:
            partner = self.env['res.partner'].sudo().search([
                ('email', '=ilike', self.from_email.strip()),
            ], limit=1)
            if partner:
                entries.append({
                    'ref': 'res.partner,%s' % partner.id,
                    'kind': 'partner',
                    'date': None,
                    'basis': 'explicit',
                })
        return entries

    def _okf_index_record(self, max_chars=None, session=None):
        """Indexera posten och bevara `.eml` på konceptet.

        Överriden för att koppla mailets råa källpost till konceptet EFTER
        att mixinen skrivit det (design.md D7). Bilagan skapas här — i
        indexerar-vägen — aldrig i `create()`.
        """
        concept = super()._okf_index_record(
            max_chars=max_chars, session=session)
        if concept:
            self._okf_attach_eml_to_concept(concept)
        return concept

    # ==================================================================
    # Registrering — kärnan ska inte känna user_mail_ai.mail
    # ==================================================================

    def _register_hook(self):
        """Registrera modellen för dirty-indexering.

        Registrering, inte överridning: `_okf_indexable_models()` är
        `@api.model` på den ABSTRAKTA modellen — en överridning här hade
        ingen verkan på cronen (mätt i kärnan 2026-09-22).
        """
        res = super()._register_hook()
        mixin = self.env['ai.okf.mixin']
        mixin._okf_register_indexable('user_mail_ai.mail')
        # D4 (2026-10-21): den här modellen driver det interaktiva
        # sökfältet (`_search_mails_okf` joinar mot den). Utan garanterad
        # andel kan en djupare kö i en annan modell svälta den — och då
        # svarar sökfältet tomt trots att posterna finns.
        mixin._okf_register_priority_indexable('user_mail_ai.mail')
        # Tidsdefault (okf-temporal-recall D4): mail är intressant BAKÅT.
        # Sju dygn är användarens val — ett kortare fönster ger skarpare
        # närtid, och avsmalningen är mjuk så det är billigt att bredda.
        mixin._okf_register_temporal_default(
            'mail', days=7, direction='backward')
        # Berikningen (D11): mail deltar som tidskandidat med
        # `received_at` och binds till en kund via `partner_id`.
        mixin._okf_register_related(
            'mail', 'user_mail_ai.mail', date_field='received_at',
            label_field='subject', partner_field='partner_id')
        # Vikt-signaler (tool-call-quality D5): `interest_score` mäter
        # INTRESSE — nyhetsbreven fick 5 och fakturan 1 i drift, så
        # "viktigaste mail" gav fel svar. Dessa tre signaler mäter VIKT.
        mixin._okf_register_importance('user_mail_ai.mail', {
            'action_required': 'action_needed',
            'due': 'follow_up_at',
            'customer': 'partner_id',
        })
        return res
