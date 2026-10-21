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

    def _okf_dirty_fields(self):
        """Fält vars ändring gör OKF-fälten inaktuella.

        Bara innehålls- och triagefält. INTE `message_id` (immutabel
        identitet), INTE `folder`/`source_uid` (pollerns bokföring), och
        INTE `memory_state`/`memory_synced_at` (skrivs av minnessynken →
        skulle självåtertända flaggan).
        """
        return {'subject', 'from_email', 'from_name', 'category',
                'status', 'notes'}

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
        return res
