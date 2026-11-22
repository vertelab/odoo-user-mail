# -*- coding: utf-8 -*-
"""Tester för OKF-kontraktet på mail (mail-okf-indexing).

Täcker:
- 3.1 konceptnyckeln `mail:<message_id>` + ägarled
- 3.2 ägare per modell (privat vs. företag)
- 3.3 body-källa
- 3.4 deterministisk summary (ingen LLM)
- 3.5 brusfiltret på user_mail_ai.mail
- 3.6 brusfiltret på mail.message
- 3.7 dirty-fält (minsta möjliga mängd)
- 4.1/4.2 ingest/repair sätter flaggan, skapar inget koncept synkront
- 5.2 mail.message utan .eml-bilaga får inte indexeringen att fela
"""

from odoo.tests.common import TransactionCase

from .test_user_mail_ai import make_raw_email


class TestOkfMail(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Mail = self.env['user_mail_ai.mail']
        self.imap = self.env['user.mail.imap']
        self.user = self.env.user

    def _ingest(self, **kw):
        """Bygg ett råmail och ingest:a det.

        RÄTTAT 2026-11-10: `folder` skickades vidare till
        `make_raw_email()`, som inte tar den parametern — två tester
        kraschade på `TypeError` i stället för att pröva brusfiltret.
        `folder` hör till `_normalize_message`, inte till råmailet.
        """
        folder = kw.pop('folder', 'INBOX')
        raw = make_raw_email(**kw)
        norm = self.imap._normalize_message(raw, folder=folder)
        return self.Mail._ingest_message(
            norm, user=self.user, raw_bytes=raw)

    # ── 2.1/2.2 mixin-arv ───────────────────────────────────────────

    def test_mixin_fields_present(self):
        for fname in ('okf_body', 'okf_summary', 'okf_links', 'okf_dirty',
                      'okf_indexed_at'):
            self.assertIn(fname, self.Mail._fields)
            self.assertIn(fname, self.env['mail.message']._fields)

    def _indexable_models(self):
        """Kortväg — attributskyddet ligger i setUp/tearDown."""
        return self.env['ai.okf.mixin']._okf_indexable_models()

    def test_registered_indexable(self):
        """Bryggan registrerar sig själv — annars får cronen aldrig kön.

        Registreringen sker i `_register_hook()` vid registry-load. Kör man
        bara den här modulens tester (`-m user_mail_ai`) kan registreringen
        ha nollställts, så testet registrerar först och återställer sedan
        listan — samma mönster som `test_registration_idempotent`.

        RÄTTAT 2026-11-10: testet läste `type(mixin)._okf_extra_indexable_models`,
        ett KLASSATTRIBUT som inte finns. Registreringen bor i modulglobalen
        `_OKF_EXTRA_INDEXABLE` — just för att Odoos testramverk fäller nya
        klassattribut på modeller. Attributåtkomsten kastade AttributeError
        i stället för att pröva det testet skulle pröva.
        """
        from odoo.addons.ai_agent_core.models.ai_okf_mixin import (
            _OKF_EXTRA_INDEXABLE)
        mixin = self.env['ai.okf.mixin']
        saved = list(_OKF_EXTRA_INDEXABLE)
        try:
            mixin._okf_register_indexable('user_mail_ai.mail')
            self.assertIn('user_mail_ai.mail',
                          mixin._okf_indexable_models())
        finally:
            _OKF_EXTRA_INDEXABLE[:] = saved

    def test_mail_message_not_registered(self):
        """`mail.message` ska INTE längre indexeras (D2, 2026-10-21).

        Modellen stod för 77,5 % av dirty-kön utan att någon läste
        koncepten — sökfältet slår mot `user_mail_ai.mail`.
        """
        models = self._indexable_models()
        self.assertNotIn('mail.message', models)

    def test_registration_idempotent(self):
        """Ett andra anrop ger ingen dubblett.

        RÄTTAT 2026-11-10 (samma fynd som `test_registered_indexable`):
        registreringen bor i modulglobalen `_OKF_EXTRA_INDEXABLE`, inte i
        ett klassattribut. Vi räddar och återställer listan IN-PLACE —
        att sätta ett nytt klassattribut hade fallit på Odoos
        attributkontroll ("Found unexpected attributes on ai.okf.mixin").
        """
        from odoo.addons.ai_agent_core.models.ai_okf_mixin import (
            _OKF_EXTRA_INDEXABLE)
        mixin = self.env['ai.okf.mixin']
        saved = list(_OKF_EXTRA_INDEXABLE)
        try:
            mixin._okf_register_indexable('user_mail_ai.mail')
            mixin._okf_register_indexable('user_mail_ai.mail')
            models = mixin._okf_indexable_models()
            self.assertEqual(models.count('user_mail_ai.mail'), 1)
        finally:
            _OKF_EXTRA_INDEXABLE[:] = saved

    # ── 3.1 konceptnyckel ───────────────────────────────────────────

    def test_concept_key_is_message_id(self):
        rec = self._ingest(message_id='<okf-key-1@example.com>')
        self.assertEqual(rec._okf_concept_key(),
                         'mail:<okf-key-1@example.com>')
        # Stabil mellan anrop.
        self.assertEqual(rec._okf_concept_key(), rec._okf_concept_key())

    def test_owner_id_adds_user_lead(self):
        rec = self._ingest(message_id='<okf-key-2@example.com>')
        owner_vals = rec._okf_owner_vals()
        owner_id = rec._okf_owner_id(owner_vals)
        self.assertEqual(owner_id, 'user.%s' % self.user.id)
        key = rec._okf_concept_key(owner_id=owner_id)
        self.assertEqual(
            key, 'mail:<okf-key-2@example.com>,user.%s' % self.user.id)

    def test_owner_id_and_lang_disambiguated(self):
        rec = self._ingest(message_id='<okf-key-3@example.com>')
        owner_id = rec._okf_owner_id(rec._okf_owner_vals())
        key = rec._okf_concept_key(lang='sv_SE', owner_id=owner_id)
        self.assertTrue(key.endswith(',user.%s,sv_SE' % self.user.id))

    # ── 3.2 ägare ───────────────────────────────────────────────────

    def test_mail_owner_is_user(self):
        rec = self._ingest(message_id='<okf-owner-1@example.com>')
        vals = rec._okf_owner_vals()
        self.assertEqual(vals.get('owner_user_id'), self.user.id)
        self.assertNotIn('owner_company_id', vals)

    def test_mail_message_owner_is_company(self):
        msg = self.env['mail.message'].create({
            'message_type': 'email',
            'subject': 'Catchall-test',
            'body': '<p>Hej från catchall</p>',
            'message_id': '<okf-catchall-1@example.com>',
            'model': 'res.partner',
            'res_id': self.user.partner_id.id,
        })
        vals = msg._okf_owner_vals()
        self.assertEqual(vals.get('owner_company_id'), self.env.company.id)
        self.assertNotIn('owner_user_id', vals)

    # ── 3.3 body ────────────────────────────────────────────────────

    def test_body_contains_subject_sender_body(self):
        rec = self._ingest(
            message_id='<okf-body-1@example.com>',
            subject='Menyn torsdag', frm='Anna <anna@example.com>',
            body='Torsdagens meny är köttbullar.')
        body = rec._okf_body_source()
        self.assertIn('Menyn torsdag', body)
        self.assertIn('anna@example.com', body)
        self.assertIn('köttbullar', body)

    def test_body_without_content_still_names_sender_and_date(self):
        """En kropp utan ämne/brödtext är inte TOM — den bär avsändare
        och datum.

        RÄTTAT 2026-11-10: testet antog att kroppen blir tom utan ämne
        och brödtext. `_okf_body_source()` för `user_mail_ai.mail` skriver
        alltid `Från:` och `Datum:` när de finns — och de finns alltid på
        ett inkommet mail. Det gamla påståendet var alltså fel om koden,
        inte ett fel i koden.

        Det som SKA prövas är att kroppen inte innehåller något som ser ut
        som innehåll: ingen brödtext, inget ämne.
        """
        rec = self._ingest(message_id='<okf-body-2@example.com>',
                           subject='', body='')
        body = rec._okf_body_source()
        self.assertIn('anna@example.com', body, 'avsändaren ska finnas')
        self.assertNotIn('Ämne:', body, 'tomt ämne ska inte skrivas ut')
        # Brödtexten bor i .eml-bilagan; utan den finns ingen text kvar.
        self.assertNotIn('köttbullar', body)

    # ── 3.4 deterministisk summary ──────────────────────────────────

    def test_summary_is_deterministic(self):
        rec = self._ingest(message_id='<okf-sum-1@example.com>',
                           subject='Faktura 123')
        first = rec._okf_summary_source()
        second = rec._okf_summary_source()
        self.assertEqual(first, second)
        self.assertIn('Faktura 123', first)

    # ── 3.5 brusfilter: user_mail_ai.mail ───────────────────────────

    def test_skip_junk_folder(self):
        rec = self._ingest(message_id='<okf-skip-junk@example.com>',
                           folder='Junk')
        self.assertTrue(rec._okf_skip_reason())

    def test_skip_trash_and_drafts(self):
        for folder in ('Trash', 'Drafts'):
            rec = self._ingest(
                message_id='<okf-skip-%s@example.com>' % folder.lower(),
                folder=folder)
            self.assertTrue(rec._okf_skip_reason(), folder)

    def test_skip_newsletter(self):
        rec = self._ingest(message_id='<okf-skip-news@example.com>')
        rec.category = 'newsletter'
        rec.status = 'classified'
        self.assertTrue(rec._okf_skip_reason())

    def test_skip_ignored(self):
        rec = self._ingest(message_id='<okf-skip-ign@example.com>')
        rec.status = 'ignored'
        self.assertTrue(rec._okf_skip_reason())

    def test_unclassified_keeps_dirty(self):
        """Oklassificerat mail ska BEHÅLLA flaggan (indexeras senare)."""
        rec = self._ingest(message_id='<okf-unclass@example.com>')
        rec.status = 'new'
        self.assertIsNone(rec._okf_skip_reason())

    def test_classified_indexed(self):
        rec = self._ingest(message_id='<okf-class@example.com>')
        rec.category = 'personal'
        rec.status = 'classified'
        self.assertIsNone(rec._okf_skip_reason())

    # ── 3.6 brusfilter: mail.message ────────────────────────────────

    def test_message_skip_non_email(self):
        msg = self.env['mail.message'].create({
            'message_type': 'comment',
            'body': '<p>chatter</p>',
        })
        self.assertTrue(msg._okf_skip_reason())

    def test_message_skip_no_object(self):
        msg = self.env['mail.message'].create({
            'message_type': 'email',
            'subject': 'Ingen koppling',
            'body': '<p>x</p>',
            'message_id': '<okf-msg-noobj@example.com>',
        })
        self.assertTrue(msg._okf_skip_reason())

    def test_message_skip_empty_body(self):
        msg = self.env['mail.message'].create({
            'message_type': 'email',
            'subject': '',
            'body': '',
            'message_id': '<okf-msg-empty@example.com>',
            'model': 'res.partner',
            'res_id': self.user.partner_id.id,
        })
        self.assertTrue(msg._okf_skip_reason())

    def test_message_email_with_object_indexed(self):
        msg = self.env['mail.message'].create({
            'message_type': 'email',
            'subject': 'Faktura till kund',
            'body': '<p>Bifogad faktura</p>',
            'message_id': '<okf-msg-ok@example.com>',
            'model': 'res.partner',
            'res_id': self.user.partner_id.id,
        })
        self.assertIsNone(msg._okf_skip_reason())
        self.assertIn('Faktura till kund', msg._okf_body_source())

    # ── 3.7 dirty-fält ──────────────────────────────────────────────

    def test_dirty_fields_minimal(self):
        rec = self._ingest(message_id='<okf-dirty-1@example.com>')
        self.assertIn('subject', rec._okf_dirty_fields())
        self.assertNotIn('memory_state', rec._okf_dirty_fields())
        self.assertNotIn('message_id', rec._okf_dirty_fields())

    def test_mail_message_dirty_fields_empty(self):
        """`mail.message` ska ha tom dirty-mängd — den indexeras inte."""
        self.assertEqual(self.env['mail.message']._okf_dirty_fields(), set())

    def test_mail_message_write_keeps_clean(self):
        """Skrivning av body/subject på mail.message ska inte sätta okf_dirty."""
        msg = self.env['mail.message'].create({
            'message_type': 'email',
            'subject': 'Faktura',
            'body': '<p>Hej</p>',
            'model': 'res.partner',
            'res_id': self.env.user.partner_id.id,
        })
        msg._clear_okf_dirty()
        self.assertFalse(msg.okf_dirty)
        msg.write({'subject': 'Nytt ämne', 'body': '<p>Nytt</p>'})
        self.assertFalse(msg.okf_dirty,
                         'mail.message ska inte längre hamna i dirty-kön')

    def test_mail_message_create_stays_clean(self):
        """Ett nytt mail ska inte hamna i kön.

        `okf_dirty` har `default=True` på mixinen och mixinens `create()`
        sätter flaggan utan att konsultera `_okf_dirty_fields()` — bara
        `write()` gör det. Utan överriden i `mail_message.create()` fylldes
        kön på igen med varje nytt mail trots avregistreringen.
        """
        msg = self.env['mail.message'].create({
            'message_type': 'email',
            'subject': 'Nytt mail',
            'body': '<p>Hej</p>',
            'model': 'res.partner',
            'res_id': self.env.user.partner_id.id,
        })
        self.assertFalse(msg.okf_dirty,
                         'ett nytt mail ska inte flaggas för indexering')

    def test_write_outside_dirty_fields_keeps_clean(self):
        rec = self._ingest(message_id='<okf-dirty-2@example.com>')
        rec._clear_okf_dirty()
        self.assertFalse(rec.okf_dirty)
        rec.write({'folder': 'Archive'})
        self.assertFalse(rec.okf_dirty)

    def test_write_inside_dirty_fields_sets_dirty(self):
        rec = self._ingest(message_id='<okf-dirty-3@example.com>')
        rec._clear_okf_dirty()
        rec.write({'subject': 'Nytt ämne'})
        self.assertTrue(rec.okf_dirty)

    # ── 4.1 ingest är billig ────────────────────────────────────────

    def test_ingest_sets_dirty_no_concept(self):
        """Ingest ska sätta okf_dirty och INTE skapa koncept synkront."""
        before = self.env['ai.okf.concept'].search_count([
            ('source_ref', '=', '<okf-ingest-1@example.com>')])
        rec = self._ingest(message_id='<okf-ingest-1@example.com>')
        self.assertTrue(rec.okf_dirty)
        after = self.env['ai.okf.concept'].search_count([
            ('source_ref', '=', '<okf-ingest-1@example.com>')])
        self.assertEqual(before, after)

    # ── 5.2 .eml saknas → ingen krasch ──────────────────────────────

    def test_index_without_eml_does_not_raise(self):
        """mail.message utan råpostbilaga får inte fela indexeringen."""
        msg = self.env['mail.message'].create({
            'message_type': 'email',
            'subject': 'Utan .eml',
            'body': '<p>Innehåll utan bilaga</p>',
            'message_id': '<okf-noeml@example.com>',
            'model': 'res.partner',
            'res_id': self.user.partner_id.id,
        })
        # Ska inte kasta; returnerar koncept eller None.
        msg._okf_index_record()
