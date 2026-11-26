# -*- coding: utf-8 -*-
"""Mail som tidsbunden kunskap (okf-temporal-recall, bryggdelen).

VARFÖR: mail är den största kunskapskällan i systemet, och en fråga om
mail är nästan alltid en fråga om TID ("vad skrev Skanska i förra
veckan"). Utan ett källdatum kunde sökningen bara filtrera på när
konceptet indexerades.

Dessa tester bevisar bryggans tre åtaganden:

  7.1  `_okf_source_date()` → mailets mottagningstid, rollen `received`
  7.2  avsändaren blir en länk till kunden — men ingen kontakt SKAPAS
  11.4 registreringen av tidsdefault (7 dygn bakåt) och berikning
"""

from datetime import datetime, timedelta

from odoo.tests import common, tagged

from .test_user_mail_ai import make_raw_email


@tagged('user_mail_ai', 'okf', 'temporal', 'post_install', '-at_install')
class TestMailTemporal(common.TransactionCase):

    def setUp(self):
        super().setUp()
        self.Mail = self.env['user_mail_ai.mail']
        self.imap = self.env['user.mail.imap']
        self.user = self.env.user
        self.Mixin = self.env['ai.okf.mixin']

    def _ingest(self, **kw):
        raw = make_raw_email(**kw)
        norm = self.imap._normalize_message(
            raw, folder=kw.get('folder', 'INBOX'))
        return self.Mail._ingest_message(
            norm, user=self.user, raw_bytes=raw)

    # ── 7.1: källdatumet ───────────────────────────────────────────────

    def test_source_date_is_the_receipt_time(self):
        """`received_at` — inte indexeringstid."""
        mail = self._ingest()
        when, role = mail._okf_source_date()
        self.assertTrue(when, 'ett mail måste ha ett källdatum')
        self.assertEqual(role, 'received')
        if mail.received_at:
            self.assertEqual(when, mail.received_at)

    def test_source_date_falls_back_to_message_create_date(self):
        """Utan `received_at` används när Odoo först såg mailet."""
        mail = self._ingest()
        mail.write({'received_at': False})
        when, role = mail._okf_source_date()
        self.assertTrue(when, 'fallback ska ge ett datum')
        self.assertEqual(role, 'received')

    def test_source_date_is_not_the_indexing_time(self):
        """Kärnan i ändringen: gamla mail ska inte se nya ut.

        Vi sätter en ankomstitid långt bakåt och prövar att det är DEN som
        returneras — inte dagens datum.
        """
        mail = self._ingest()
        old = datetime.now() - timedelta(days=400)
        mail.write({'received_at': old})
        when, _role = mail._okf_source_date()
        self.assertEqual(when, old)

    def test_received_at_is_a_dirty_field(self):
        """Task 3.4: en rättad ankomstitid ska slå igenom."""
        self.assertIn('received_at', self.Mail._okf_dirty_fields())

    def test_partner_is_a_dirty_field(self):
        """Kundlänken är en del av konceptets mening."""
        self.assertIn('partner_id', self.Mail._okf_dirty_fields())

    # ── 7.2: avsändaren blir en länk ───────────────────────────────────

    def test_known_sender_is_linked_through_partner_id(self):
        """Känd avsändare → `partner_id` → mixinens generiska länk.

        FYND 2026-11-10: `_resolve_partner()` SKAPAR kontakten redan vid
        ingest, så `partner_id` är alltid satt. Länken läggs därför av
        mixinens relationsfält — `_okf_links_extra()` behöver inte göra
        det, och ska inte lägga en dubblett.
        """
        partner = self.env['res.partner'].create({
            'name': 'Skanska Test AB',
            'email': 'kund@skanska-test.se',
        })
        mail = self._ingest(frm='Skanska <kund@skanska-test.se>')
        self.assertEqual(mail.partner_id, partner,
                         'ingest ska matcha den befintliga kontakten')
        links = mail._okf_links_source()
        refs = [e['ref'] if isinstance(e, dict) else e for e in links]
        self.assertIn('res.partner,%s' % partner.id, refs,
                      'mixinens relationsfält ska länka kunden')
        extra = [e['ref'] for e in mail._okf_links_extra()]
        self.assertNotIn('res.partner,%s' % partner.id, extra,
                         'ingen dubblett från _okf_links_extra')

    def test_extra_never_creates_a_partner(self):
        """`_okf_links_extra()` får aldrig skapa en kontakt.

        Ingest kan göra det (det är triagens jobb), men länkningen får
        inte ha sidoeffekter i databasen.
        """
        mail = self._ingest(frm='Okand <okand@finns-inte.example>')
        before = self.env['res.partner'].search_count([])
        mail._okf_links_extra()
        after = self.env['res.partner'].search_count([])
        self.assertEqual(before, after, 'ingen kontakt får skapas')

    def test_object_model_becomes_a_link(self):
        """Triage-kopplingen (sträng + id) blir en typad länk."""
        mail = self._ingest()
        mail.write({'object_model': 'res.partner',
                    'object_res_id': 1})
        entries = mail._okf_links_extra()
        refs = [e['ref'] for e in entries]
        self.assertIn('res.partner,1', refs)
        entry = [e for e in entries if e['ref'] == 'res.partner,1'][0]
        self.assertEqual(entry['basis'], 'explicit')

    def test_links_carry_the_typed_shape(self):
        mail = self._ingest()
        mail.write({'object_model': 'res.partner', 'object_res_id': 2})
        entry = [e for e in mail._okf_links_extra()
                 if e['ref'] == 'res.partner,2'][0]
        for key in ('ref', 'kind', 'date', 'basis'):
            self.assertIn(key, entry, 'länken måste vara typad')

    def test_existing_partner_link_is_not_duplicated(self):
        """Har triage redan satt `partner_id` ska vi inte lägga en till."""
        partner = self.env['res.partner'].create({
            'name': 'Dubbel Test',
            'email': 'dubbel@test.example',
        })
        mail = self._ingest(frm='Dubbel <dubbel@test.example>')
        mail.write({'partner_id': partner.id})
        refs = [e['ref'] for e in mail._okf_links_extra()]
        self.assertNotIn(
            'res.partner,%s' % partner.id, refs,
            'mixinens relationsfält lägger redan den länken')

    # ── 11.4: registreringen ───────────────────────────────────────────

    def test_temporal_default_is_registered(self):
        """Mail defaultar 7 dygn BAKÅT."""
        defaults = self.Mixin._okf_temporal_defaults()
        self.assertIn('mail', defaults)
        self.assertEqual(defaults['mail']['days'], 7)
        self.assertEqual(defaults['mail']['direction'], 'backward')

    def test_related_registration(self):
        """Mail deltar i berikningen med received_at och partner_id."""
        registry = self.Mixin._okf_related_models()
        self.assertIn('user_mail_ai.mail', registry)
        cfg = registry['user_mail_ai.mail']
        self.assertEqual(cfg['date_field'], 'received_at')
        self.assertEqual(cfg['partner_field'], 'partner_id')
        self.assertEqual(cfg['kind'], 'mail')
