# -*- coding: utf-8 -*-
"""Tester för user-mail-ai-rules — create_object / create_activity,
partner-uppslagning, HITL-provlage, seed-regler och dubblettskydd."""

import json

from odoo.tests.common import TransactionCase


def make_raw_email(message_id='<rules-1@example.com>', subject='Test',
                   frm='Anna <anna@example.com>', to='kalle@vertel.se',
                   body='Hej Kalle!\nHär är ett testmail.'):
    from email.message import EmailMessage
    msg = EmailMessage()
    msg['Message-ID'] = message_id
    msg['Subject'] = subject
    msg['From'] = frm
    msg['To'] = to
    msg['Date'] = 'Mon, 05 Aug 2026 10:00:00 +0200'
    msg.set_content(body)
    return msg.as_bytes()


class TestRulesObjects(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Mail = self.env['user_mail_ai.mail']
        self.Rule = self.env['user_mail_ai.rule']
        self.imap = self.env['user.mail.imap']
        self.user = self.env.user
        self.coworker = self.env.ref(
            'user_mail_ai.coworker_mail_assistant', raise_if_not_found=False) \
            or self.env['ai.coworker'].create({
                'name': 'Mail-hjälpredan', 'status': 'active',
                'orchestration_mode': 'single'})

    def _ingest(self, raw=None, frm='Anna <anna@example.com>', **kw):
        raw = raw or make_raw_email(frm=frm, **kw)
        norm = self.imap._normalize_message(raw, folder='INBOX')
        return self.Mail._ingest_message(
            norm, user=self.user, raw_bytes=raw)

    def _rule(self, model, **cfg):
        action_config = dict(cfg)
        action_config.setdefault('model', model)
        action_config.setdefault('hitl', False)
        # Match the production seed rules: without a partner config the
        # sender is never resolved and partner_id stays empty.
        action_config.setdefault('partner', {
            'mode': 'link_or_create',
            'create_company': True,
            'contact_from_sender': True,
        })
        return self.Rule.create({
            'user_id': self.user.id,
            'name': 'Test %s' % model,
            'priority': 1,
            'condition_kind': 'sender',
            'condition_text': 'anna@example.com',
            'action': 'create_object',
            'action_config': json.dumps(action_config),
        })

    # ── 8.1 Skapa lead från ny partner ──────────────────────────────

    def test_create_object_lead_opportunity(self):
        rec = self._ingest(frm='Ny Kunds <ny@kund.se>')
        rule = self._rule('crm.lead', defaults={'type': 'opportunity'},
                          partner={'mode': 'link_or_create'},
                          activity={'type': 'Call', 'summary': 'Följ upp'})
        handled = rec._create_object(rule)
        self.assertTrue(handled)
        self.assertEqual(rec.object_model, 'crm.lead')
        lead = self.env['crm.lead'].browse(rec.object_res_id)
        self.assertEqual(lead.type, 'opportunity')
        self.assertTrue(lead.partner_id, 'Leaden ska länkas till partnern')
        self.assertEqual(lead.partner_id.email, 'ny@kund.se')
        # Aktiviteten ska ha mailägaren som ansvarig
        activity = self.env['mail.activity'].search([
            ('res_model', '=', 'crm.lead'), ('res_id', '=', lead.id)])
        self.assertTrue(activity)
        self.assertEqual(activity.user_id, self.user)

    # ── 8.2 Känd partner länkas (ingen dubblett) ────────────────────

    def test_create_object_lead_known_partner(self):
        partner = self.env['res.partner'].create({
            'name': 'Känd Kund', 'email': 'kand@kund.se'})
        rec = self._ingest(frm='Känd <kand@kund.se>')
        rule = self._rule('crm.lead', defaults={'type': 'opportunity'})
        rec._create_object(rule)
        lead = self.env['crm.lead'].browse(rec.object_res_id)
        self.assertEqual(lead.partner_id, partner)
        self.assertEqual(self.env['res.partner'].search_count([
            ('email', '=ilike', 'kand@kund.se')]), 1,
            'Ingen ny partner ska skapas för känd avsändare')

    # ── 8.3 Fri e-posttjänst → inget företag ────────────────────────

    def test_resolve_partner_free_mail(self):
        rec = self._ingest()
        rec.write({'from_email': 'privat@gmail.com', 'from_name': 'Privat'})
        partner = rec._resolve_sender_partner({
            'mode': 'link_or_create', 'create_company': True,
            'contact_from_sender': True})
        self.assertTrue(partner)
        self.assertFalse(partner.is_company)
        self.assertFalse(partner.parent_id,
                         'Gmail ska inte skapa ett företag')

    # ── 8.4 mode='link' utan träff → ingen partner ──────────────────

    def test_resolve_partner_link_mode(self):
        rec = self._ingest()
        rec.write({'from_email': 'okand-xyz@nowhere.se'})
        partner = rec._resolve_sender_partner({'mode': 'link'})
        self.assertFalse(partner)
        self.assertEqual(self.env['res.partner'].search_count([
            ('email', '=ilike', 'okand-xyz@nowhere.se')]), 0)

    # ── 8.5 Okänd modell → varning, inget krasch ────────────────────

    def test_create_object_unknown_model(self):
        rec = self._ingest()
        rule = self._rule('nonexistent.model')
        handled = rec._create_object(rule)
        self.assertFalse(handled)
        self.assertFalse(rec.object_model)

    # ── 8.6 Aktivitetens ägare är mailägaren ────────────────────────

    def test_create_activity_owner_is_mail_owner(self):
        other = self.env['res.users'].create({
            'name': 'Other', 'login': 'other-rules@example.com'})
        rec = self._ingest()
        # Kör i annan användares kontext — ägaren ska ändå vara mailägaren
        rec_as_other = self.Mail.with_user(other).sudo().browse(rec.id)
        self.assertEqual(rec_as_other.env.user, other)
        rec_as_other._create_activity(
            'res.partner', self.user.partner_id.id,
            {'type': 'To-Do', 'summary': 'Owner check'})
        activity = self.env['mail.activity'].search([
            ('res_model', '=', 'res.partner'),
            ('res_id', '=', self.user.partner_id.id),
            ('summary', '=', 'Owner check')], limit=1)
        self.assertTrue(activity)
        self.assertEqual(activity.user_id, self.user,
                         'Aktiviteten ska hamna hos mailägaren, inte env.user')

    # ── 8.7 Ogiltiga LLM-fält filtreras ─────────────────────────────

    def test_llm_fields_filtered(self):
        rec = self._ingest()
        vals = {'name': 'Rubrik', 'bogus_field': 'x', 'type': 'opportunity'}
        filtered = rec._filter_vals('crm.lead', vals)
        self.assertIn('name', filtered)
        self.assertIn('type', filtered)
        self.assertNotIn('bogus_field', filtered)

    # ── 8.8 Dubblett-ärende länkas, inte skapas ─────────────────────

    def test_duplicate_ticket_linked_not_created(self):
        ticket = self.env['helpdesk.ticket'].create({
            'name': 'Samma ärende', 'partner_email': 'anna@example.com',
            'description': 'Befintligt ärende'})
        rec = self._ingest()
        rule = self._rule('helpdesk.ticket')
        before = self.env['helpdesk.ticket'].search_count([
            ('partner_email', '=ilike', 'anna@example.com'),
            ('name', '=', 'Samma ärende')])
        handled = rec._do_create_object(
            rule, 'helpdesk.ticket', {'name': 'Samma ärende'})
        self.assertTrue(handled)
        after = self.env['helpdesk.ticket'].search_count([
            ('partner_email', '=ilike', 'anna@example.com'),
            ('name', '=', 'Samma ärende')])
        self.assertEqual(before, after, 'Inget nytt ärende ska skapas')
        self.assertEqual(rec.object_res_id, ticket.id,
                         'Mailet ska länkas till det befintliga ärendet')

    # ── 8.9 Provläge: upprepat godkännande → aldrig autonomt ────────

    def test_hitl_always_in_probe_mode(self):
        rec = self._ingest()
        rule = self._rule('crm.lead', defaults={'type': 'opportunity'},
                          hitl=True)
        # HITL kräver en körningssession (ai_agent_core design D7)
        session = self.env['ai.coworker.session'].create({
            'coworker_id': self.coworker.id,
            'user_id': self.user.id,
            'status': 'active',
            'name': 'Probe-mode test run',
        })
        rec = rec.with_context(
            _ai_context_model='ai.coworker.session',
            _ai_context_id=session.id)
        # Första matchningen → HITL-förslag, inget objekt
        self.assertTrue(rec._create_object(rule))
        self.assertFalse(rec.object_model, 'Inget objekt före godkännande')
        hitl = self.env['ai.coworker.hitl'].search([
            ('action_type', '=', 'create_object'),
            ('object_type', '=', 'crm.lead')], limit=1)
        self.assertTrue(hitl)
        hitl.with_user(self.user).action_approve()
        self.assertEqual(rec.object_model, 'crm.lead')
        # Regeln är INTE autonom — en ny matchning begär godkännande igen
        self.assertTrue(rule._parse_config().get('hitl', True),
                        'hitl ska förbli True — ingen trust-ladder')
        self.assertFalse(hasattr(rule, '_rule_is_trusted'),
                         'Ingen trust-ladder ska finnas')

    # ── 8.10 Seed-regler skapas inaktiva ────────────────────────────

    def test_seed_rules_created_inactive(self):
        self.user.imap_password = self.user._encrypt_imap_pw('x')
        self.user.write({'imap_poll_enabled': True})
        self.Mail._ensure_default_rules()
        seeds = self.Rule.with_context(active_test=False).search([
            ('user_id', '=', self.user.id), ('source', '=', 'seed')])
        self.assertEqual(len(seeds), 7, 'Sju seed-regler ska skapas')
        obj_rules = seeds.filtered(lambda r: r.action == 'create_object')
        self.assertEqual(len(obj_rules), 4)
        for rule in obj_rules:
            self.assertFalse(rule.active,
                             'Objektskapande seed-regler ska vara inaktiva')
            self.assertTrue(rule._parse_config().get('hitl'),
                            'Provläge: hitl ska vara True')
        others = seeds.filtered(lambda r: r.action != 'create_object')
        for rule in others:
            self.assertTrue(rule.active, 'Reglerna 1–3 ska vara aktiva')

    # ── 8.11 create_object short-circuitar ──────────────────────────

    def test_apply_rules_create_object_short_circuits(self):
        rec = self._ingest()
        self._rule('crm.lead', defaults={'type': 'opportunity'})
        self.Rule.create({
            'user_id': self.user.id, 'name': 'Låg prio ignore',
            'priority': 50, 'condition_kind': 'sender',
            'condition_text': 'anna@example.com', 'action': 'ignore'})
        handled, nudged = rec._apply_rules()
        self.assertTrue(handled)
        self.assertFalse(nudged)
        self.assertEqual(rec.object_model, 'crm.lead')
        self.assertNotEqual(rec.status, 'ignored',
                            'create_object ska short-circuita ignore-regeln')

    # ── Extra: create_activity på kopplat objekt ────────────────────

    def test_create_activity_on_linked_object(self):
        partner = self.env['res.partner'].create({
            'name': 'Länkad', 'email': 'lankad@example.com'})
        rec = self._ingest()
        rec.write({'object_link_candidate': json.dumps({
            'model': 'res.partner', 'res_id': partner.id,
            'source': 'llm'})})
        rule = self.Rule.create({
            'user_id': self.user.id, 'name': 'Aktivitet på partner',
            'priority': 1, 'condition_kind': 'sender',
            'condition_text': 'anna@example.com',
            'action': 'create_activity',
            'action_config': json.dumps({
                'model': 'res.partner', 'hitl': False,
                'activity': {'type': 'To-Do', 'summary': 'Ring upp'}}),
        })
        handled = rec._create_activity_on_object(rule)
        self.assertTrue(handled)
        activity = self.env['mail.activity'].search([
            ('res_model', '=', 'res.partner'), ('res_id', '=', partner.id),
            ('summary', '=', 'Ring upp')], limit=1)
        self.assertTrue(activity)
        self.assertEqual(activity.user_id, self.user)

    # ── Extra: helpdesk-team fallback ───────────────────────────────

    def test_helpdesk_team_fallback(self):
        rec = self._ingest()
        rule = self._rule('helpdesk.ticket')
        rec._do_create_object(
            rule, 'helpdesk.ticket', {'name': 'Nytt ärende'})
        ticket = self.env['helpdesk.ticket'].browse(rec.object_res_id)
        self.assertTrue(ticket.team_id,
                        'Utan team_id i config ska första teamet användas')

    # ── Extra: konfigurerat team används ────────────────────────────

    def test_helpdesk_team_configured(self):
        team = self.env['helpdesk.ticket.team'].search([], limit=1)
        if not team:
            self.skipTest('Inget helpdesk-team finns')
        rec = self._ingest()
        rule = self._rule('helpdesk.ticket', team_id=team.id)
        rec._do_create_object(
            rule, 'helpdesk.ticket', {'name': 'Konfigurerat ärende'})
        ticket = self.env['helpdesk.ticket'].browse(rec.object_res_id)
        self.assertEqual(ticket.team_id, team)

    # ── Extra: joplin.note skapas med källa ─────────────────────────

    def test_create_object_joplin_note(self):
        if 'joplin.note' not in self.env:
            self.skipTest('knowledge_joplin är inte installerad')
        rec = self._ingest()
        rule = self._rule('joplin.note', defaults={
            'source': 'mail', 'source_application': 'user_mail_ai'})
        # Via _create_object so the rule's action_config is the source of
        # truth — the same path the cron takes.
        handled = rec._create_object(rule)
        self.assertTrue(handled)
        note = self.env['joplin.note'].browse(rec.object_res_id)
        self.assertTrue(note.joplin_id, 'joplin_id ska genereras av modellen')
        self.assertEqual(note.user_id, self.user)
        self.assertEqual(note.source, 'mail')
        self.assertEqual(note.source_application, 'user_mail_ai')

    # ── Extra: konfigurationsvalidering ─────────────────────────────

    def test_create_object_joplin_note_no_llm_fields(self):
        """joplin.note without title/user_id from the LLM must still create.

        Both are NOT NULL in the DB and are not part of the rule defaults,
        so a failed LLM extraction must not abort the create.
        """
        if 'joplin.note' not in self.env:
            self.skipTest('knowledge_joplin är inte installerad')
        rec = self._ingest()
        # No llm_fields and no title/user_id in defaults.
        rule = self._rule('joplin.note', defaults={'source': 'mail'})
        handled = rec._create_object(rule)
        self.assertTrue(handled, 'anteckningen ska skapas ändå')
        note = self.env['joplin.note'].browse(rec.object_res_id)
        self.assertTrue(note.title, 'title ska falla tillbaka på ämnet')
        self.assertEqual(note.user_id, self.user,
                         'user_id ska sättas till mailägaren')

    def test_create_object_requires_model(self):
        from odoo.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            self.Rule.create({
                'user_id': self.user.id, 'name': 'Utan modell',
                'condition_kind': 'sender', 'condition_text': 'x',
                'action': 'create_object', 'action_config': '{}'})
