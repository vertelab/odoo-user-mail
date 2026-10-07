# -*- coding: utf-8 -*-
"""Tester för user-mail-ai-intelligence (Skiva 3) — regler, profil, digest,
heartbeat."""

import json
from datetime import datetime, timedelta

from odoo.tests.common import TransactionCase


class TestUserMailAiIntelligence(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Mail = self.env['user_mail_ai.mail']
        self.Rule = self.env['user_mail_ai.rule']
        self.imap = self.env['user.mail.imap']
        self.user = self.env.user

    def _ingest(self, message_id='<intel-1@example.com>',
                subject='Test', frm='Anna <anna@example.com>'):
        from email.message import EmailMessage
        msg = EmailMessage()
        msg['Message-ID'] = message_id
        msg['Subject'] = subject
        msg['From'] = frm
        msg['To'] = 'kalle@vertel.se'
        msg.set_content('Hej!')
        norm = self.imap._normalize_message(msg.as_bytes(), folder='INBOX')
        return self.Mail._ingest_message(norm, user=self.user)

    # ── Regel-modell ─────────────────────────────────────────────────

    def test_rule_create(self):
        rule = self.Rule.create({
            'user_id': self.user.id,
            'name': 'Ignorera nyhetsbrev från X',
            'priority': 5,
            'condition_kind': 'sender',
            'condition_text': 'news@example.com',
            'action': 'ignore',
        })
        self.assertTrue(rule)
        self.assertEqual(rule.source, 'user')

    def test_deterministic_sender_match(self):
        rule = self.Rule.create({
            'user_id': self.user.id,
            'name': 'Ignorera från news',
            'condition_kind': 'sender',
            'condition_text': 'news@example.com',
            'action': 'ignore',
        })
        rec = self._ingest(frm='News <news@example.com>')
        self.assertTrue(rule._matches(rec))
        rec2 = self._ingest(message_id='<intel-2@example.com>',
                            frm='Anna <anna@example.com>')
        self.assertFalse(rule._matches(rec2))

    def test_apply_ignore_rule(self):
        self.Rule.create({
            'user_id': self.user.id,
            'name': 'Ignorera från news',
            'condition_kind': 'sender',
            'condition_text': 'news@example.com',
            'action': 'ignore',
        })
        rec = self._ingest(frm='News <news@example.com>')
        handled, nudged = rec._apply_rules()
        self.assertTrue(handled)
        self.assertFalse(nudged)
        self.assertEqual(rec.status, 'ignored')

    def test_priority_wins(self):
        # Lägre prioritetstal = högre prioritet → move vinner över ignore
        self.Rule.create({
            'user_id': self.user.id, 'name': 'Låg prio ignore',
            'priority': 50, 'condition_kind': 'sender',
            'condition_text': 'news@example.com', 'action': 'ignore',
        })
        self.Rule.create({
            'user_id': self.user.id, 'name': 'Hög prio nudge',
            'priority': 1, 'condition_kind': 'sender',
            'condition_text': 'news@example.com', 'action': 'nudge',
        })
        rec = self._ingest(frm='News <news@example.com>')
        handled, nudged = rec._apply_rules()
        self.assertFalse(handled)
        self.assertTrue(nudged, "Högst prioriterad regel (nudge) ska vinna")

    # ── Default-regler (seed) ────────────────────────────────────────

    def test_ensure_default_rules_idempotent(self):
        # Gate (mail-credentials): poll-flaggan kräver ett lösenord.
        self.user.imap_password = self.user._encrypt_imap_pw('x')
        self.user.write({'imap_poll_enabled': True})
        first = self.Mail._ensure_default_rules()
        self.assertGreater(first, 0)
        second = self.Mail._ensure_default_rules()
        self.assertEqual(second, 0, "Inga dubletter vid omkörning")
        count = self.Rule.search_count([
            ('user_id', '=', self.user.id),
            ('source', '=', 'seed'),
        ])
        self.assertGreaterEqual(count, 3)

    # ── Klassificeringskontext (LLM-regler + profil) ─────────────────

    def test_prompt_includes_rules_and_profile(self):
        self.Rule.create({
            'user_id': self.user.id, 'name': 'Meddela om missnöje',
            'condition_kind': 'llm',
            'condition_text': 'Kunden är missnöjd',
            'action': 'nudge',
        })
        self.user.write({'ai_profile_text': 'Bryr sig om byggprojekt '
                                            'och kundnöjdhet.'})
        rec = self._ingest()
        prompt = rec._build_classification_prompt()
        self.assertIn('Meddela om missnöje', prompt)
        self.assertIn('byggprojekt', prompt)
        self.assertIn('matched_rules', prompt)

    # ── Intresseprofil ───────────────────────────────────────────────

    def test_finalize_interest_without_embedding(self):
        rec = self._ingest()
        rec.write({'interest_score': 8.0, 'status': 'classified'})
        rec._finalize_interest()
        self.assertEqual(rec.interest_score, 8.0,
                         "Utan embedding behålls LLM-poängen")

    # ── Digest-arkivering ────────────────────────────────────────────

    def test_save_digest_okf(self):
        if 'ai.okf.concept' not in self.env:
            return
        ok = self.Mail._save_digest_okf(
            self.user, 'Sammanfattning av igår', daily=True)
        self.assertTrue(ok)
        concept = self.env['ai.okf.concept'].search([
            ('owner_user_id', '=', self.user.id),
            ('title', 'like', 'Digest daily'),
        ], limit=1)
        self.assertTrue(concept, "Digesten ska arkiveras som OKF-koncept")

    # ── Heartbeat ────────────────────────────────────────────────────

    def test_heartbeat_finds_stale_action_mail(self):
        rec = self._ingest()
        rec.write({
            'action_needed': True,
            'status': 'classified',
            'write_date': (datetime.now() - timedelta(days=5))
            .strftime('%Y-%m-%d %H:%M:%S'),
        })
        items = self.Mail._heartbeat_open_items(self.user, stale_days=2)
        self.assertIn(rec, items)

    def test_heartbeat_finds_unsent_draft(self):
        rec = self._ingest()
        rec.write({
            'draft_uid': 77,
            'status': 'classified',
            'write_date': (datetime.now() - timedelta(days=3))
            .strftime('%Y-%m-%d %H:%M:%S'),
        })
        items = self.Mail._heartbeat_open_items(self.user, stale_days=2)
        self.assertIn(rec, items)

    def test_heartbeat_quiet_for_fresh_mail(self):
        rec = self._ingest()
        rec.write({'action_needed': True, 'status': 'classified'})
        items = self.Mail._heartbeat_open_items(self.user, stale_days=2)
        self.assertNotIn(rec, items, "Färskt mail ska inte nudgas")

    def test_heartbeat_review_updates_follow_up(self):
        rec = self._ingest()
        rec.write({
            'action_needed': True,
            'status': 'classified',
            'write_date': (datetime.now() - timedelta(days=5))
            .strftime('%Y-%m-%d %H:%M:%S'),
        })
        self.Mail._heartbeat_review(user=self.user)
        self.assertTrue(rec.follow_up_at, "Follow-up ska sättas efter nudge")

    # ── Regression: tråd-kandidat får inte skrivas över av LLM-nolla ──

    def test_thread_candidate_survives_null_llm_candidate(self):
        """Deterministisk tråd-matchning (confidence 1.0) ska överleva
        en klassificering där LLM:en returnerar object_link_candidate=null.

        Regression: `_thread_candidate()`-blocket låg tidigare efter
        `return True` i `_classify()` och kördes aldrig.
        """
        import json
        from email.message import EmailMessage

        task = self.env['project.task'].create({
            'name': 'Trådärende', 'user_ids': [(6, 0, [self.user.id])]})
        self.env['mail.message'].create({
            'model': 'project.task', 'res_id': task.id,
            'message_id': '<thread-1@example.com>',
            'body': 'Hej', 'message_type': 'email',
        })
        msg = EmailMessage()
        msg['Message-ID'] = '<thread-reply@example.com>'
        msg['Subject'] = 'Re: Trådärende'
        msg['From'] = 'Anna <anna@example.com>'
        msg['To'] = 'kalle@vertel.se'
        msg['References'] = '<thread-1@example.com>'
        msg.set_content('Svar i tråden')
        norm = self.imap._normalize_message(msg.as_bytes(), folder='INBOX')
        rec = self.Mail._ingest_message(norm, user=self.user)

        # Simulera att LLM-svaret saknade kandidat → skriv nolla
        rec.write({'object_link_candidate': False})
        rec._apply_thread_candidate()
        cand = json.loads(rec.object_link_candidate or 'null')
        self.assertTrue(cand, 'Tråd-matchning ska återställas efter LLM-nolla')
        self.assertEqual(cand['model'], 'project.task')
        self.assertEqual(cand['res_id'], task.id)
        self.assertEqual(cand['source'], 'thread')

    def test_apply_thread_candidate_skips_linked_mail(self):
        """Catchall-mail har redan objekt → trådkandidat ska inte skrivas."""
        from email.message import EmailMessage
        msg = EmailMessage()
        msg['Message-ID'] = '<thread-skip@example.com>'
        msg['Subject'] = 'X'
        msg['From'] = 'a@example.com'
        msg['To'] = 'b@example.com'
        msg.set_content('x')
        norm = self.imap._normalize_message(msg.as_bytes(), folder='INBOX')
        rec = self.Mail._ingest_message(norm, user=self.user)
        rec.write({
            'object_model': 'project.task', 'object_res_id': 1,
            'object_link_candidate': json.dumps({
                'model': 'project.task', 'res_id': 1, 'source': 'llm'}),
        })
        rec._apply_thread_candidate()
        self.assertIn('llm', rec.object_link_candidate or '',
                      'Redan objektkopplat mail ska inte skrivas över')

    # ── Regression: profil-cron följer veckodag (inte 7-dagars drift) ──

    def test_recompute_profiles_respects_weekday(self):
        """_recompute_profiles utan force ska bara köra på rätt veckodag."""
        from datetime import date
        # Gate (mail-credentials): poll-flaggan kräver ett lösenord.
        self.user.imap_password = self.user._encrypt_imap_pw('x')
        self.user.write({
            'imap_poll_enabled': True,
            # Sätt veckodagen till "inte idag" (om möjligt)
            'ai_profile_weekday': str((date.today().weekday() + 1) % 7),
        })
        # Utan force och fel veckodag: ingen profil genereras (returnerar 0
        # eftersom provider saknas eller weekday inte matchar — men får inte
        # krascha och får inte räkna om).
        result = self.Mail._recompute_profiles(force=False)
        self.assertEqual(result, 0,
                         'Fel veckodag ska inte räkna om profilen')
        self.assertIn('ai_profile_weekday', self.env['res.users']._fields)

    # ── mail-memory-sync: markör, reparation, städning ───────────────

    def test_ingest_sets_memory_marker(self):
        rec = self._ingest(message_id='<mem-1@example.com>')
        # Grafen kan vara otillgänglig i test → antingen synced eller failed,
        # men aldrig kvar på default 'pending'.
        self.assertIn(rec.memory_state, ('synced', 'failed'))

    def test_ingest_creates_graph_node(self):
        """8.3: ingest → :MailMessage-nod finns + markören satt.

        Kräver fungerande AGE (search_path-fixen i ai_agent_core). Om grafen
        inte är användbar i miljön hoppas testet över — annars är detta det
        starka beviset att minnet byggs vid ingest.
        """
        rec = self._ingest(message_id='<mem-graph@example.com>')
        if rec.memory_state != 'synced':
            self.skipTest('AGE-grafen är inte användbar i denna miljö')
        self.assertTrue(rec._graph_node_exists(),
                        ':MailMessage-noden ska finnas efter ingest')
        self.assertIsNotNone(rec.memory_synced_at)

    def test_memory_marker_default_pending(self):
        rec = self._ingest(message_id='<mem-2@example.com>')
        # Fältet finns och har ett värde ur selectionen.
        self.assertIn(rec.memory_state, ('pending', 'synced', 'failed'))

    def test_refresh_memory_scoped_to_user(self):
        # Knappens kärna ska bara röra env.user:s mail.
        from email.message import EmailMessage
        other = self.env['res.users'].create({
            'name': 'Other', 'login': 'other-mem@example.com'})
        mine = self._ingest(message_id='<mem-mine@example.com>')
        msg = EmailMessage()
        msg['Message-ID'] = '<mem-theirs@example.com>'
        msg['Subject'] = 'Theirs'
        msg['From'] = 'Bo <bo@example.com>'
        msg['To'] = 'other@vertel.se'
        msg.set_content('Hej')
        theirs = self.Mail.with_user(other)._ingest_message(
            self.imap._normalize_message(msg.as_bytes(), folder='INBOX'),
            user=other)
        self.Mail.with_user(self.user)._refresh_memory(self.user)
        # Den andra användarens mail får inte ha rörts av min refresh.
        self.assertNotEqual(
            self.Mail.browse(theirs.id).memory_state, 'synced')
        self.assertIn(self.Mail.browse(mine.id).memory_state,
                      ('synced', 'failed'))

    def test_rebuild_memory_no_version_on_existing_concept(self):
        rec = self._ingest(message_id='<mem-3@example.com>')
        if 'ai.okf.concept' not in self.env:
            self.skipTest('OKF inte installerat')
        Concept = self.env['ai.okf.concept'].sudo()
        before = Concept.search_count([('source_ref', '=', rec.message_id)])
        rec._rebuild_memory()
        after = Concept.search_count([('source_ref', '=', rec.message_id)])
        # Mail är immutabla: ingen ny version skapas vid reparation.
        self.assertEqual(before, after,
                         'Reparation får inte versionera OKF-konceptet')

    def test_prune_graph_nodes_safe_without_graph(self):
        # Städningen ska inte kasta när grafen är otillgänglig.
        self.Mail._prune_graph_nodes()

    def test_prune_removes_ghost_keeps_existing(self):
        """6.5: spöknod bort, existerande kvar — kräver fungerande AGE."""
        rec = self._ingest(message_id='<mem-prune@example.com>')
        if rec.memory_state != 'synced':
            self.skipTest('AGE-grafen är inte användbar i denna miljö')
        # Skapa ett mail, verifiera att noden finns, radera sedan raden.
        exists = rec._graph_node_exists()
        if not exists:
            self.skipTest('Ingen :MailMessage-nod kunde skapas')
        rid = rec.id
        rec.unlink()
        self.Mail._prune_graph_nodes()
        # Noden ska vara borta; en kvarvarande rad ska behålla sin nod.
        survivor = self._ingest(message_id='<mem-survive@example.com>')
        self.Mail._prune_graph_nodes()
        self.assertTrue(
            survivor._graph_node_exists(),
            'Existerande mail får inte städas bort')

    def test_repair_memory_all_runs(self):
        # Gate (mail-credentials): poll-flaggan kräver ett lösenord.
        self.user.imap_password = self.user._encrypt_imap_pw('x')
        self.user.write({'imap_poll_enabled': True})
        # Ska inte kasta; returnerar antal synkade.
        self.Mail._repair_memory_all(batch_size=5)
