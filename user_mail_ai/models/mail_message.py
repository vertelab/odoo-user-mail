# -*- coding: utf-8 -*-
"""Catchall/Discuss-ingestion + OKF-kontrakt för mail.message.

Två ansvar i samma fil (samma modell):

1. **Ingest-hook** (`create`): mail som Odoo fångat (mailgateway) → triage.
   Filtrering:
   - message_type='email' + icke-intern subtype (kommentarer/notiser skippas)
   - avsändare får inte vara en intern användare (våra egna svar skippas)
   - hjälpredans egna posts sätts med context-flaggan user_mail_ai_no_ingest
   - Message-ID-dedup skyddar mot dubbel med IMAP-pollen (Skiva 1)

2. **OKF-kontrakt** (`ai.okf.mixin`): catchall-mailen (info@ → crm.lead)
   blir sökbar kunskap i Odoo Mind. Ägs av FÖRETAGET (delad brevlåda),
   till skillnad från `user_mail_ai.mail` (privat brevlåda, ägs av
   användaren). Access följer källdokumentet (`model`/`res_id`), inte
   mottagarlistan — samma modell som Odoos egen `mail.message._search()`.

VARFÖR `_inherit` och inte core-patch: Odoo tillåter att en brygga utökar
en core-modell utan att röra core. `bridges`-specen kräver att domän-core
förblir ren, och `mail` är Odoo-core.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


def _okf_message_type_is_email(message_type):
    """Bara inkommande e-post är kunskap. Utgående och notiser är brus."""
    return message_type == 'email'


class MailMessageAI(models.Model):
    _name = 'mail.message'
    _inherit = ['mail.message', 'ai.okf.mixin']

    # OKF-taggar: egen relationstabell (en many2many kan inte ligga på en
    # abstrakt mixin — den ger samma tabell för alla ärvande modeller).
    okf_tags = fields.Many2many(
        'ai.okf.tag', 'mail_message_okf_tag_rel', 'res_id', 'tag_id',
        string='OKF Tags')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get('user_mail_ai_no_ingest'):
            return records
        for rec in records:
            try:
                self._maybe_ingest(rec)
            except Exception as e:
                _logger.warning('Mail ingest hook failed (%s): %s',
                                rec.id, e)
        return records

    def _maybe_ingest(self, rec):
        """Ingestera inkommande email-mail → samma triage-pipeline."""
        if rec.message_type != 'email':
            return
        if rec.subtype_id and rec.subtype_id.internal:
            return
        if not rec.model or not rec.res_id:
            return
        if rec.author_id:
            user = self.env['res.users'].search(
                [('partner_id', '=', rec.author_id.id)], limit=1)
            if user:
                # Avsändaren är en intern användare (vårt eget svar) → skippa
                return
        try:
            self.env['user_mail_ai.mail']._ingest_mail_message(rec)
        except Exception as e:
            _logger.warning('Ingest mail.message %s failed: %s', rec.id, e)

    # ==================================================================
    # OKF-kontraktet — catchall-mailen blir kunskap
    # ==================================================================

    def _okf_body_source(self):
        """Ämne, avsändare, datum, källobjekt och brödtext.

        ÖVERRIDEN — den generiska defaulten läser alla HTML/Text-fält +
        `name`. För mail.message är `body` rätt, men `preview`,
        `record_name` och diverse chatter-metadata är brus; vi vill bara
        ha e-postens innehåll.
        """
        self.ensure_one()
        parts = []
        if self.subject:
            parts.append('Ämne: %s' % self.subject)
        if self.email_from:
            parts.append('Från: %s' % self.email_from)
        if self.date:
            parts.append('Datum: %s' % self.date)
        if self.model and self.res_id:
            parts.append('Kopplat till: %s,%s' % (self.model, self.res_id))
        if self.body:
            parts.append(self._okf_html_to_text(self.body))
        return '\n\n'.join(parts)

    def _okf_summary_source(self, owner_vals=None):
        """DETERMINISTISK sammanfattning — ingen LLM.

        Ämne + avsändare + datum + källobjekt. Catchall-mail kan vara
        många; en LLM-tur per mail vore dyrt och varierar mellan körningar.
        """
        self.ensure_one()
        bits = []
        if self.subject:
            bits.append(self.subject)
        if self.email_from:
            bits.append('från %s' % self.email_from)
        if self.date:
            bits.append('(%s)' % self.date)
        if self.model and self.res_id:
            bits.append('[%s,%s]' % (self.model, self.res_id))
        return ' '.join(bits) or None

    def _okf_dirty_fields(self):
        """Fält vars ändring gör OKF-fälten inaktuella.

        Minsta möjliga mängd — `mail.message` är en av Odoos mest
        trafikerade modeller. `body` och `subject` är innehållet; allt
        annat (message_type, model, res_id) sätts vid skapandet och ändras
        sällan. Hooken läser bara fältnamnen i `vals` — billigt.
        """
        return {'body', 'subject'}

    def _okf_concept_key(self, lang=None, owner_id=None):
        """`mail:<message_id>` — samma nyckel som user_mail_ai.mail.

        Ett brev i catchall och samma brev i en privat brevlåda är olika
        koncept (olika ägare), men samma brev routat två gånger ger samma
        nyckel → en version, inte en dubblett.
        """
        self.ensure_one()
        base = 'mail:%s' % (self.message_id or 'id:%s' % self.id)
        if owner_id:
            base = '%s,%s' % (base, owner_id)
        if lang:
            base = '%s,%s' % (base, lang)
        return base

    def _okf_owner_vals(self):
        """Catchall är delad — konceptet ägs av företaget.

        Access prövas via källdokumentet (`model`/`res_id`), inte via
        mottagarlistan (design.md D6). Ett koncept per följare skulle
        explodera (100 mail × 50 följare).
        """
        self.ensure_one()
        return {'owner_company_id': self.env.company.id}

    def _okf_artifact_type(self):
        """Bryggans egen typ — spårbar till user_mail_ai i taxonomin."""
        return 'mail'

    def _okf_skip_reason(self):
        """Brusfiltret för catchall-mail.

        Avför: icke-e-post (chatter-kommentarer, notiser), interna
        subtyper, tomt innehåll och mail utan affärsobjekt. Returnerar en
        sträng = "medvetet avförd" (flaggan rensas).
        """
        self.ensure_one()
        if not _okf_message_type_is_email(self.message_type):
            return 'message_type=%s' % (self.message_type or '?')
        if self.subtype_id and self.subtype_id.internal:
            return 'intern subtype %s' % self.subtype_id.name
        if not self.model or not self.res_id:
            return 'inget affärsobjekt'
        if not (self.body or '').strip() and not (self.subject or '').strip():
            return 'tomt mail'
        return None

    # ==================================================================
    # Registrering — kärnan ska inte känna mail.message
    # ==================================================================

    def _register_hook(self):
        """Registrera mail.message för dirty-indexering.

        Registrering, inte överridning: `_okf_indexable_models()` är
        `@api.model` på den ABSTRAKTA modellen — en överridning här hade
        ingen verkan på cronen (mätt i kärnan 2026-09-22).
        """
        res = super()._register_hook()
        self.env['ai.okf.mixin']._okf_register_indexable('mail.message')
        return res
