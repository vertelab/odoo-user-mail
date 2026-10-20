from odoo.tests.common import TransactionCase


class TestImap(TransactionCase):

    def setUp(self):
        super().setUp()
        self.imap = self.env['user.mail.imap']
        self.user = self.env.user
        self.user.write({'password': 'test123'})

    def test_password_encryption_on_write(self):
        self.assertTrue(self.user.imap_password, "imap_password should be set after password write")
        decrypted = self.user._decrypt_imap_pw()
        self.assertEqual(decrypted, 'test123')

    def test_encryption_key_generated(self):
        key = self.env['ir.config_parameter'].get_param('user_mail_imap.encryption_key')
        self.assertTrue(key, "Encryption key should exist in config")

    def test_write_updates_imap_password(self):
        self.user.write({'password': 'newpass456'})
        decrypted = self.user._decrypt_imap_pw()
        self.assertEqual(decrypted, 'newpass456')

    def test_create_sets_imap_password(self):
        user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'test@example.com',
            'password': 'createpass',
        })
        self.assertTrue(user.imap_password, "imap_password should be set on create")
        decrypted = user._decrypt_imap_pw()
        self.assertEqual(decrypted, 'createpass')

    def test_encrypt_decrypt_roundtrip(self):
        pw = 'my_secret_password!123'
        encrypted = self.user._encrypt_imap_pw(pw)
        self.assertNotEqual(encrypted, pw, "Encrypted should differ from plaintext")
        self.user.imap_password = encrypted
        decrypted = self.user._decrypt_imap_pw()
        self.assertEqual(decrypted, pw)

    def test_empty_password_returns_none(self):
        self.user.imap_password = False
        result = self.user._decrypt_imap_pw()
        self.assertIsNone(result)

    def test_model_exists(self):
        # user.mail.imap är en AbstractModel — den har inga records, så
        # assertTrue(recordset) är alltid falskt. Kontrollera namnet.
        self.assertEqual(self.imap._name, 'user.mail.imap')
        self.assertEqual(self.imap._description, 'IMAP Mail Operations')

    def test_model_fields(self):
        user_fields = self.env['res.users'].fields_get()
        self.assertIn('imap_password', user_fields, "res.users should have imap_password field")

    # ── Credentials: verifiering mot dovecot_password + gate ─────────

    def test_verify_dovecot_password_match(self):
        from passlib.hash import sha512_crypt
        self.user.dovecot_password = sha512_crypt.hash('hemligt')
        self.assertTrue(self.user._verify_dovecot_password('hemligt'))

    def test_verify_dovecot_password_mismatch(self):
        from passlib.hash import sha512_crypt
        self.user.dovecot_password = sha512_crypt.hash('hemligt')
        self.assertFalse(self.user._verify_dovecot_password('fel'))

    def test_verify_dovecot_password_no_hash(self):
        self.user.dovecot_password = False
        self.assertIsNone(self.user._verify_dovecot_password('vad-som-helst'))

    def test_action_set_imap_password_verifies(self):
        from passlib.hash import sha512_crypt
        self.user.dovecot_password = sha512_crypt.hash('hemligt')
        self.user.imap_password = False
        self.user.action_set_imap_password('hemligt')
        self.assertEqual(self.user._decrypt_imap_pw(), 'hemligt')

    def test_action_set_imap_password_rejects_wrong(self):
        from odoo.exceptions import UserError
        from passlib.hash import sha512_crypt
        self.user.dovecot_password = sha512_crypt.hash('hemligt')
        self.user.imap_password = False
        with self.assertRaises(UserError):
            self.user.action_set_imap_password('fel')
        self.assertFalse(self.user.imap_password)

    def test_action_set_imap_password_without_hash(self):
        self.user.dovecot_password = False
        self.user.imap_password = False
        self.user.action_set_imap_password('nytt-losenord')
        self.assertEqual(self.user._decrypt_imap_pw(), 'nytt-losenord')

    def test_poll_enabled_requires_password(self):
        from odoo.exceptions import UserError
        self.user.imap_password = False
        self.user.imap_poll_enabled = False
        with self.assertRaises(UserError):
            self.user.write({'imap_poll_enabled': True})

    def test_poll_enabled_with_password_ok(self):
        self.user.imap_password = self.user._encrypt_imap_pw('x')
        self.user.write({'imap_poll_enabled': True})
        self.assertTrue(self.user.imap_poll_enabled)

    def test_poll_disable_always_allowed(self):
        self.user.imap_password = False
        self.user.imap_poll_enabled = False
        self.user.write({'imap_poll_enabled': False})
        self.assertFalse(self.user.imap_poll_enabled)

    def test_poll_skips_user_without_password(self):
        # Användare med poll-flagga men utan lösenord ska hoppas över tyst.
        self.env.cr.execute(
            "UPDATE res_users SET imap_poll_enabled = true, "
            "imap_password = NULL WHERE id = %s", (self.user.id,))
        self.user.invalidate_recordset()
        # Ska inte kasta trots saknat lösenord.
        self.imap.action_poll_all()

    def test_preferences_exposes_mail_fields(self):
        # Min profil (view_users_form_simple_modif) filtrerar mot
        # SELF_READABLE_FIELDS/SELF_WRITEABLE_FIELDS — utan överridningen
        # renderas gruppen tom och flaggan kan inte sparas.
        readable = self.env['res.users'].SELF_READABLE_FIELDS
        writeable = self.env['res.users'].SELF_WRITEABLE_FIELDS
        for f in ('imap_password', 'imap_poll_enabled', 'last_imap_sync'):
            self.assertIn(f, readable, f'{f} måste vara self-readable')
        self.assertIn('imap_poll_enabled', writeable,
                      'imap_poll_enabled måste vara self-writeable')
        self.assertNotIn('imap_password', writeable,
                         'lösenordet sätts via wizarden, inte via formuläret')

    def test_preferences_save_persists_poll_flag(self):
        # 4.5: fältet ska faktiskt sparas när användaren ändrar sig själv
        # via preferences (write sker som användaren, inte sudo).
        self.user.imap_password = self.user._encrypt_imap_pw('x')
        self.user.with_user(self.user).write({'imap_poll_enabled': True})
        self.assertTrue(
            self.env['res.users'].browse(self.user.id).imap_poll_enabled)

    # ── Poller (normalisering, dedup, modeller) ──────────────────────

    def _make_raw_email(self, message_id='<test-1@example.com>', subject='Hej',
                        frm='Anna <anna@example.com>', to='kalle@vertel.se',
                        body='Test body', add_ics=False):
        from email.message import EmailMessage
        msg = EmailMessage()
        msg['Message-ID'] = message_id
        msg['Subject'] = subject
        msg['From'] = frm
        msg['To'] = to
        msg['Date'] = 'Mon, 05 Aug 2026 10:00:00 +0200'
        msg.set_content(body)
        if add_ics:
            # Python 3.12: bytes → raw_data_manager (tillåter maintype/
            # subtype); en str skulle gå till text-managern och kasta.
            msg.add_attachment(
                b'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n',
                filename='invite.ics', maintype='text', subtype='calendar')
        return msg.as_bytes()

    def test_normalize_message(self):
        raw = self._make_raw_email()
        norm = self.imap._normalize_message(raw, folder='INBOX')
        self.assertEqual(norm['message_id'], '<test-1@example.com>')
        self.assertEqual(norm['subject'], 'Hej')
        self.assertIn('anna@example.com', norm['from_'])
        self.assertEqual(norm['folder'], 'INBOX')
        self.assertIn('Test body', norm['body_text'])
        self.assertEqual(norm['dedup_key'], '<test-1@example.com>')

    def test_normalize_message_with_ics_attachment(self):
        raw = self._make_raw_email(add_ics=True)
        norm = self.imap._normalize_message(raw)
        self.assertTrue(any(
            a['filename'] == 'invite.ics' for a in norm['attachments']))

    def test_dedup_key_fallback_hash(self):
        norm = {
            'from_': 'anna@example.com',
            'subject': 'Hej',
            'date': 'Mon, 05 Aug 2026 10:00:00 +0200',
        }
        key = self.imap._dedup_key(norm)
        self.assertTrue(key.startswith('h:'), "Fallback key should be hashed")

    def test_processed_unique_constraint(self):
        user = self.env.user
        self.env['user.mail.processed'].create({
            'user_id': user.id, 'message_id': 'dup-1'})
        with self.assertRaises(Exception):
            self.env['user.mail.processed'].create({
                'user_id': user.id, 'message_id': 'dup-1'})

    def test_poll_model_and_fields(self):
        # user.mail.poll är konkret men tom → kontrollera namnet, inte
        # sanningsvärdet av ett tomt recordset.
        self.assertEqual(
            self.env['user.mail.poll']._name, 'user.mail.poll')
        self.assertTrue('imap_poll_enabled' in self.env['res.users']._fields)
        self.assertTrue('last_imap_sync' in self.env['res.users']._fields)
        self.assertFalse(self.env.user.imap_poll_enabled,
                         "Poll ska vara opt-in per användare")

    # ── Poll-flödet med mockad IMAP (7.3-kärnan, utan riktig server) ──

    def test_poll_user_updates_last_imap_sync(self):
        """7.3: poll → last_imap_sync uppdateras.

        Mockar IMAP4_SSL så hela flödet (connect → search → fetch →
        normalisera → _on_new_messages → last_imap_sync) kan verifieras utan
        en riktig brevlåda. Det är mekanismen 7.3 vill bekräfta; den riktiga
        servern krävs bara för att bekräfta nätverksdelen.
        """
        from unittest.mock import patch, MagicMock
        from email.message import EmailMessage

        self.user.imap_password = self.user._encrypt_imap_pw('x')
        self.user.last_imap_sync = False
        self.user.imap_poll_enabled = True
        # Pollern kräver postfix_mail (IMAP-login-namnet). Sätt den direkt —
        # postfix_mail är ett compute-fält som annars kräver postfix_active.
        self.user.postfix_mail = 'poll-test@vertel.se'

        msg = EmailMessage()
        msg['Message-ID'] = '<poll-test-1@example.com>'
        msg['Subject'] = 'Poll-test'
        msg['From'] = 'Anna <anna@example.com>'
        msg['To'] = 'kalle@vertel.se'
        msg['Date'] = 'Mon, 05 Aug 2026 10:00:00 +0200'
        msg.set_content('Hej!')
        raw = msg.as_bytes()

        fake = MagicMock()
        fake.select.return_value = ('OK', [b'1'])
        fake.response.return_value = ('UIDVALIDITY', [b'42'])
        fake.search.return_value = ('OK', [b'1'])
        fake.fetch.return_value = ('OK', [(b'1 (BODY[] {123}', raw)])
        fake.login.return_value = ('OK', [b'logged in'])

        def _uid(cmd, *args):
            if cmd == 'SEARCH':
                return ('OK', [b'1'])
            if cmd == 'FETCH':
                spec = args[1]
                if 'HEADER.FIELDS' in spec:
                    return ('OK', [(b'1 (UID 1 BODY[HEADER] {1}',
                                    b'Message-ID: <poll-test-1@example.com>\r\n'
                                    b'Subject: Poll-test\r\n'
                                    b'From: Anna <anna@example.com>\r\n'
                                    b'Date: Mon, 05 Aug 2026 10:00:00 +0200\r\n\r\n')])
                return ('OK', [(b'1 (UID 1 BODY[] {123}', raw)])
            return ('OK', [b''])
        fake.uid.side_effect = _uid

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            n, failed = self.env['user.mail.imap'].with_user(
                self.user).action_poll_user()

        self.assertEqual(n, 1, 'ett nytt mail ska pollas')
        self.assertEqual(failed, 0, 'inget normaliseringsfel')
        self.assertTrue(self.user.last_imap_sync,
                        'last_imap_sync ska sättas efter lyckad poll')
        # Readonly-säkerhet: BODY.PEEK, aldrig STORE (flaggor).
        fetch_calls = [c for c in fake.uid.call_args_list
                       if c[0][0] == 'FETCH']
        self.assertTrue(fetch_calls, 'pollern ska hämta meddelandet')
        self.assertTrue(any('BODY.PEEK' in str(c[0][2]) for c in fetch_calls),
                        'hämtning ska använda BODY.PEEK')
        self.assertFalse(fake.store.called, 'pollern får aldrig sätta flaggor')

    def test_poll_skips_when_no_password(self):
        """Pollern hoppar över användare utan lösenord (ingen UserError)."""
        from unittest.mock import patch
        # action_poll_all() söker ALLA användare med imap_poll_enabled.
        # I en TransactionCase ser den även riktiga användare, och en sådan
        # med lösenord skulle ansluta skarpt mot produktionsbrevlådan. Lås
        # sökningen till testanvändaren så testet blir isolerat.
        self.user.imap_password = False
        self.env.cr.execute(
            "UPDATE res_users SET imap_poll_enabled = true, "
            "imap_password = NULL WHERE id = %s", (self.user.id,))
        self.user.invalidate_recordset()
        with patch('imaplib.IMAP4_SSL') as m, \
                patch.object(type(self.env['res.users']), 'search',
                             return_value=self.user):
            self.env['user.mail.imap'].action_poll_all()
            self.assertFalse(m.called,
                             'ingen IMAP-anslutning ska göras utan lösenord')

    # ── Mail-länkar: _prepare_body_html (fix-mail-link-target) ──

    def test_prepare_body_html_adds_target(self):
        """Länkar i mail-HTML ska öppnas i nytt fönster."""
        from odoo.addons.user_mail_imap.models.imap_server import (
            _prepare_body_html)
        out = _prepare_body_html('<a href="https://example.com">x</a>')
        self.assertIn('target="_blank"', out)
        self.assertIn('rel="noopener noreferrer"', out)

    def test_prepare_body_html_preserves_existing_target(self):
        """En länk som redan har target ska lämnas orörd."""
        from odoo.addons.user_mail_imap.models.imap_server import (
            _prepare_body_html)
        src = '<a href="x" target="_self">y</a>'
        self.assertEqual(_prepare_body_html(src), src)

    def test_prepare_body_html_skips_fragments_and_anchors(self):
        """Ankare och href utan värde ska inte få target."""
        from odoo.addons.user_mail_imap.models.imap_server import (
            _prepare_body_html)
        # Rena fragmentlänkar stannar i samma dokument.
        self.assertEqual(_prepare_body_html('<a href="#a">x</a>'),
                         '<a href="#a">x</a>')
        self.assertEqual(_prepare_body_html("<a href='#a'>x</a>"),
                         "<a href='#a'>x</a>")
        # <a name="..."> är inget länkmål.
        self.assertEqual(_prepare_body_html('<a name="a">x</a>'),
                         '<a name="a">x</a>')

    def test_prepare_body_html_handles_single_quotes_and_case(self):
        """Mail-HTML använder ofta enkelcitat och versaler."""
        from odoo.addons.user_mail_imap.models.imap_server import (
            _prepare_body_html)
        self.assertIn('target="_blank"', _prepare_body_html("<a href='x'>y</a>"))
        self.assertIn('target="_blank"', _prepare_body_html('<A HREF="x">y</A>'))

    def test_prepare_body_html_passthrough_empty(self):
        """Tom/None-HTML ska passera oförändrad."""
        from odoo.addons.user_mail_imap.models.imap_server import (
            _prepare_body_html)
        self.assertIsNone(_prepare_body_html(None))
        self.assertEqual(_prepare_body_html(''), '')

    # ── Sökning: action_search_mails (add-imap-mail-search) ──

    def test_search_mails_builds_nested_or_criteria(self):
        """Sökningen ska täcka FROM, SUBJECT och TEXT (nästlad OR)."""
        from unittest.mock import patch, MagicMock
        from email.message import EmailMessage

        self.user.imap_password = self.user._encrypt_imap_pw('x')
        self.user.postfix_mail = 'search-test@vertel.se'

        msg = EmailMessage()
        msg['Message-ID'] = '<search-1@example.com>'
        msg['Subject'] = 'Faktura 123'
        msg['From'] = 'Anna <anna@example.com>'
        msg['Date'] = 'Mon, 05 Aug 2026 10:00:00 +0200'
        msg.set_content('Hej!')
        raw = msg.as_bytes()

        fake = MagicMock()
        fake.select.return_value = ('OK', [b'1'])
        fake.search.return_value = ('OK', [b'1'])
        fake.fetch.return_value = ('OK', [(b'1 (BODY[] {123}', raw)])
        fake.login.return_value = ('OK', [b'logged in'])

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            res = self.env['user.mail.imap'].with_user(self.user)\
                .action_search_mails('INBOX', 'faktura', 0, 80)

        self.assertEqual(res['total'], 1)
        self.assertEqual(res['messages'][0]['subject'], 'Faktura 123')
        # IMAP:s OR tar två argument — tre kriterier kräver nästling.
        criteria = fake.search.call_args[0][1]
        self.assertIn('FROM "faktura"', criteria)
        self.assertIn('SUBJECT "faktura"', criteria)
        self.assertIn('TEXT "faktura"', criteria)
        self.assertTrue(criteria.startswith('OR OR'),
                        'tre kriterier ska nästlas som OR OR a b c')

    def test_search_mails_escapes_quotes(self):
        """Citattecken i sökordet får inte bryta IMAP-strängen."""
        from unittest.mock import patch, MagicMock

        self.user.imap_password = self.user._encrypt_imap_pw('x')
        self.user.postfix_mail = 'search-test@vertel.se'

        fake = MagicMock()
        fake.select.return_value = ('OK', [b'1'])
        fake.search.return_value = ('OK', [b''])
        fake.login.return_value = ('OK', [b'logged in'])

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(self.user)\
                .action_search_mails('INBOX', 'a"b', 0, 80)

        criteria = fake.search.call_args[0][1]
        self.assertIn('\\"', criteria, 'citattecken ska escapas')
        self.assertNotIn('"a"b"', criteria, 'osparad sträng får inte uppstå')

    def test_search_mails_empty_query_returns_nothing(self):
        """Tom sökning ska inte öppna en IMAP-anslutning."""
        from unittest.mock import patch

        self.user.imap_password = self.user._encrypt_imap_pw('x')
        self.user.postfix_mail = 'search-test@vertel.se'

        with patch('imaplib.IMAP4_SSL') as m:
            res = self.env['user.mail.imap'].with_user(self.user)\
                .action_search_mails('INBOX', '   ', 0, 80)

        self.assertEqual(res, {'messages': [], 'total': 0})
        self.assertFalse(m.called, 'ingen anslutning för tom sökning')

    def test_search_mails_handles_failed_search(self):
        """Misslyckad SEARCH ska ge tomt resultat, inte krascha."""
        from unittest.mock import patch, MagicMock

        self.user.imap_password = self.user._encrypt_imap_pw('x')
        self.user.postfix_mail = 'search-test@vertel.se'

        fake = MagicMock()
        fake.select.return_value = ('OK', [b'1'])
        fake.search.return_value = ('NO', [b'error'])
        fake.login.return_value = ('OK', [b'logged in'])

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            res = self.env['user.mail.imap'].with_user(self.user)\
                .action_search_mails('INBOX', 'x', 0, 80)

        self.assertEqual(res, {'messages': [], 'total': 0})

    # ── Poll-budget: cursor, dedup-före-fetch, budget (fix-imap-poll-cron-backlog) ──

    def _poll_user(self):
        """Pollande testanvändare med postfix_mail satt (compute annars)."""
        self.user.imap_password = self.user._encrypt_imap_pw('x')
        self.user.imap_poll_enabled = True
        self.env.flush_all()
        self.user.postfix_mail = 'budget-test@vertel.se'
        self.user.last_imap_sync = False
        self.user.last_imap_uid = 0
        self.user.last_imap_uidvalidity = False
        return self.user

    @staticmethod
    def _fake_conn(uids, headers=None, bodies=None, uidvalidity='42'):
        """Minimal IMAP-dubbel som svarar på UID SEARCH/FETCH och SELECT."""
        from unittest.mock import MagicMock
        fake = MagicMock()
        # imaplib.select() returnerar BARA EXISTS; UIDVALIDITY ligger i
        # untagged_responses och läses med response(). Att mocka select()
        # att returnera UIDVALIDITY dolde en bugg där koden letade på fel
        # ställe och alltid fick None.
        fake.select.return_value = ('OK', [str(len(uids)).encode()])
        fake.response.return_value = (
            'UIDVALIDITY', [('UIDVALIDITY %s' % uidvalidity).encode()])
        fake.login.return_value = ('OK', [b'logged in'])
        fake.uid.return_value = ('OK', [b' '.join(str(u).encode() for u in uids)])

        headers = headers or {}
        bodies = bodies or {}

        def _uid(cmd, *args):
            if cmd == 'SEARCH':
                return ('OK', [b' '.join(str(u).encode() for u in uids)])
            if cmd == 'FETCH':
                uid_set, spec = args[0], args[1]
                ids = [int(x) for x in str(uid_set).split(',')]
                if 'HEADER.FIELDS' in spec:
                    out = []
                    for u in ids:
                        if u in headers:
                            out.append((b'%d (UID %d BODY[HEADER] {1}' % (u, u),
                                        headers[u]))
                    return ('OK', out)
                out = []
                for u in ids:
                    if u in bodies:
                        out.append((b'%d (UID %d BODY[] {1}' % (u, u), bodies[u]))
                return ('OK', out)
            return ('OK', [b''])
        fake.uid.side_effect = _uid
        return fake

    @staticmethod
    def _header_bytes(message_id, subject='Test', sender='a@b.se'):
        return ('Message-ID: %s\r\nSubject: %s\r\nFrom: %s\r\n'
                'Date: Mon, 05 Aug 2026 10:00:00 +0200\r\n\r\n'
                % (message_id, subject, sender)).encode()

    @staticmethod
    def _body_bytes(message_id, subject='Test'):
        from email.message import EmailMessage
        msg = EmailMessage()
        msg['Message-ID'] = message_id
        msg['Subject'] = subject
        msg['From'] = 'a@b.se'
        msg['Date'] = 'Mon, 05 Aug 2026 10:00:00 +0200'
        msg.set_content('Hej!')
        return msg.as_bytes()

    def test_cursor_uses_uid_search_not_since(self):
        """Med satt cursor ska pollern göra UID SEARCH UID n+1:* — inte SINCE."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 100
        user.last_imap_uidvalidity = '42'
        self.env.flush_all()
        fake = self._fake_conn([], uidvalidity='42')

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(user).action_poll_user()

        search_args = [c for c in fake.uid.call_args_list
                       if c[0][0] == 'SEARCH']
        self.assertTrue(search_args, 'pollern ska göra UID SEARCH')
        self.assertIn('UID 101:*', str(search_args[0][0]))
        self.assertFalse(fake.search.called,
                         'SINCE-vägen får inte användas när cursor finns')

    def test_no_cursor_falls_back_to_all(self):
        """Utan cursor görs en engångs-omsynkronisering (SEARCH ALL)."""
        from unittest.mock import patch
        user = self._poll_user()
        fake = self._fake_conn([], uidvalidity='42')

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(user).action_poll_user()

        search_args = [c for c in fake.uid.call_args_list
                       if c[0][0] == 'SEARCH']
        self.assertIn('ALL', str(search_args[0][0]))

    def test_uidvalidity_change_resets_cursor(self):
        """Ändrad UIDVALIDITY ska nollställa cursorn (resync)."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 500
        user.last_imap_uidvalidity = 'OLD'
        self.env.flush_all()
        fake = self._fake_conn([], uidvalidity='NEW')

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(user).action_poll_user()

        user.invalidate_recordset()
        self.assertEqual(user.last_imap_uidvalidity, 'NEW')
        search_args = [c for c in fake.uid.call_args_list
                       if c[0][0] == 'SEARCH']
        self.assertIn('ALL', str(search_args[0][0]),
                      'resync ska söka ALL, inte UID 501:*')

    def test_dedup_before_full_body_fetch(self):
        """Redan processat mail får aldrig ett BODY.PEEK[]-anrop."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 0
        user.last_imap_uidvalidity = '42'
        self.env['user.mail.processed'].create({
            'user_id': user.id,
            'message_id': '<seen-1@example.com>',
        })
        self.env.flush_all()
        self.assertEqual(
            self.env['user.mail.imap']._dedup_key(
                {'message_id': '<seen-1@example.com>'}),
            '<seen-1@example.com>',
            'dedup-nyckeln ska vara Message-ID när det finns')
        headers = {1: self._header_bytes('<seen-1@example.com>')}
        fake = self._fake_conn([1], headers=headers,
                               bodies={1: self._body_bytes('<seen-1@example.com>')})

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            n, _failed = self.env['user.mail.imap'].with_user(
                user).action_poll_user()

        self.assertEqual(n, 0, 'redan processat mail ska inte räknas som nytt')
        full_fetches = [c for c in fake.uid.call_args_list
                        if c[0][0] == 'FETCH' and 'HEADER.FIELDS' not in c[0][2]]
        self.assertFalse(full_fetches,
                         'dedup ska ske före full body-fetch')

    def test_budget_zero_processes_nothing(self):
        """Budget 0 s: inga meddelanden bearbetas, inget kastas."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 0
        user.last_imap_uidvalidity = '42'
        self.env['ir.config_parameter'].sudo().set_param(
            'user_mail_imap.poll_budget_seconds', '0')
        headers = {1: self._header_bytes('<b1@example.com>')}
        fake = self._fake_conn([1], headers=headers,
                               bodies={1: self._body_bytes('<b1@example.com>')})

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            n, _failed = self.env['user.mail.imap'].with_user(
                user).action_poll_user()

        self.assertEqual(n, 0)

    def test_poison_message_advances_cursor(self):
        """Ett mail som inte kan normaliseras blockar inte brevlådan."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 0
        user.last_imap_uidvalidity = '42'
        headers = {7: self._header_bytes('<poison@example.com>')}
        poison = (b'Message-ID: <poison@example.com>\r\n'
                  b'Subject: x\r\n'
                  b'Content-Type: text/plain; charset="x-unknown-charset"\r\n'
                  b'Content-Transfer-Encoding: base64\r\n\r\n'
                  b'!!!not-base64!!!\r\n')
        fake = self._fake_conn([7], headers=headers, bodies={7: poison})
        self.env.flush_all()

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(user).action_poll_user()

        user.invalidate_recordset()
        self.assertEqual(user.last_imap_uid, 7,
                         'cursorn ska avancera förbi det trasiga mailet')
        row = self.env['user.mail.processed'].search([
            ('user_id', '=', user.id),
            ('message_id', '=', '<poison@example.com>'),
        ])
        self.assertTrue(row, 'det trasiga mailet ska spåras')
        self.assertTrue(row.failed, 'raden ska vara markerad som misslyckad')
        self.assertTrue(row.failure_reason,
                        'felorsaken ska vara läsbar utan att läsa loggen')

    def test_poll_health_reports_parse_errors(self):
        """_poll_health() ska räkna misslyckade mail senaste dygnet."""
        user = self.env['res.users'].create({
            'name': 'Poll Health User',
            'login': 'poll-health@vertel.se',
            'password': 'x',
        })
        user.imap_password = user._encrypt_imap_pw('x')
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE res_users SET imap_poll_enabled = true WHERE id = %s",
            (user.id,))
        user.invalidate_recordset()
        self.env.cr.execute(
            "SELECT imap_poll_enabled FROM res_users WHERE id = %s",
            (user.id,))
        self.assertTrue(self.env.cr.fetchone()[0],
                        'testanvändaren ska vara pollande i DB')
        self.env.invalidate_all()
        self.env['user.mail.processed'].create({
            'user_id': user.id,
            'message_id': '<fail@example.com>',
            'failed': True,
            'failure_reason': 'MessageError: boom',
        })
        self.env.cr.execute(
            "SELECT id, imap_poll_enabled, active FROM res_users "
            "WHERE imap_poll_enabled = true")
        rows = self.env.cr.fetchall()
        self.assertIn(user.id, [r[0] for r in rows],
                      'DB ska visa användaren som pollande: %r' % (rows,))
        found = self.env['res.users'].sudo().search(
            [('imap_poll_enabled', '=', True)])

        self.assertIn(user, found,
                      'användaren ska hittas av samma sökning som _poll_health gör')
        health = self.env['user.mail.poll']._poll_health()
        self.assertIn(user.login, health)
        self.assertEqual(health[user.login]['parse_errors_24h'], 1)
        for key in ('last_run', 'last_ok', 'truncated',
                    'parse_errors_24h', 'backlog_estimate'):
            self.assertIn(key, health[user.login])

    # ── INC-2026-10-19: minnesfotavtryck ────────────────────────────

    def test_normalize_message_carries_no_raw_bytes(self):
        """Råbytes får inte bäras i den normaliserade formen.

        Fältet `raw` kopierade hela meddelandet (inkl. bilagor) in i
        dict:en, och en poll bygger en lista av alla normaliserade mail —
        hela brevlådan låg i minnet samtidigt (RSS 500 MB -> 2 336 MB på
        sju minuter, `virtual memory limit reached` 0,1-0,3 s efter
        pollens slut).
        """
        raw = self._make_raw_email()
        norm = self.imap._normalize_message(raw, folder='INBOX')
        self.assertNotIn('raw', norm,
                         'normaliserat mail får inte bära råbytes')

    def test_normalize_message_hands_raw_to_sink(self):
        """Råbytes lämnas till raw_sink medan de ännu finns i handen."""
        raw = self._make_raw_email()
        seen = []

        def sink(norm, raw_bytes):
            seen.append((norm['message_id'], raw_bytes))

        norm = self.imap._normalize_message(
            raw, folder='INBOX', raw_sink=sink)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], '<test-1@example.com>')
        self.assertEqual(seen[0][1], raw)
        self.assertNotIn('raw', norm)

    def test_normalize_message_carries_thread_refs(self):
        """Trådreferenser bärs som korta strängar — inte som råbytes."""
        from email.message import EmailMessage
        msg = EmailMessage()
        msg['Message-ID'] = '<reply@example.com>'
        msg['Subject'] = 'Re: Hej'
        msg['From'] = 'Anna <anna@example.com>'
        msg['To'] = 'kalle@vertel.se'
        msg['Date'] = 'Mon, 05 Aug 2026 10:00:00 +0200'
        msg['In-Reply-To'] = '<parent@example.com>'
        msg['References'] = '<parent@example.com> <grandparent@example.com>'
        msg.set_content('Svar')
        norm = self.imap._normalize_message(msg.as_bytes())
        self.assertIn('<parent@example.com>', norm['thread_refs'])
        self.assertIn('<grandparent@example.com>', norm['thread_refs'])

    def test_raw_sink_failure_does_not_break_normalization(self):
        """En trasig sink får inte fälla normaliseringen."""
        raw = self._make_raw_email()

        def broken_sink(norm, raw_bytes):
            raise RuntimeError('sink is broken')

        norm = self.imap._normalize_message(
            raw, folder='INBOX', raw_sink=broken_sink)
        self.assertEqual(norm['message_id'], '<test-1@example.com>')

    def test_mail_cache_purges_by_ttl(self):
        """Cachen ska rensa på tid, inte bara på storlek.

        En cache som bara töms när den passerar ett antal poster håller
        sina poster kvar så länge ingen ny post läggs till — och
        `body_html` för 500 mail är inte trivialt.
        """
        from odoo.addons.user_mail_imap.models import imap_server
        imap_server._mail_cache.clear()
        imap_server._mail_cache['stale'] = (0.0, {'body_html': 'gammal'})
        imap_server._mail_cache['fresh'] = (
            imap_server.time.monotonic(), {'body_html': 'ny'})
        imap_server._purge_mail_cache(ttl=60)
        self.assertNotIn('stale', imap_server._mail_cache)
        self.assertIn('fresh', imap_server._mail_cache)
        imap_server._mail_cache.clear()

    def _capture_logs(self, logger_name):
        """Fånga loggrader oberoende av Odoos log_handler.

        Odoo kör tester med `-l test`, som sätter loggernivån så att INFO
        undertrycks. `assertLogs` fångar bara det som faktiskt når loggern,
        så vi hänger på en egen handler och höjer nivån under testet.
        """
        import logging
        logger = logging.getLogger(logger_name)
        records = []

        class _Handler(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = _Handler()
        old_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        return logger, handler, records, old_level

    def test_logout_failures_are_reported_summarized(self):
        """Upprepade LOGOUT-fel ska ge en loggrad, inte en per förekomst."""
        from odoo.addons.user_mail_imap.models import imap_server
        imap_server._LOGOUT_FAILURES.clear()
        for _ in range(20):
            imap_server._LOGOUT_FAILURES.append('LOGOUT => Return-Path: x')
        logger, handler, records, old_level = self._capture_logs(
            'odoo.addons.user_mail_imap.models.imap_server')
        try:
            imap_server._report_logout_failures('anna@example.com')
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
        self.assertEqual(
            len(records), 1,
            'tjugo identiska LOGOUT-fel ska bli EN sammanfattande rad')
        self.assertIn('x20', records[0].getMessage())
        self.assertEqual(imap_server._LOGOUT_FAILURES, [],
                         'räknaren ska nollställas efter rapportering')

    def test_poll_writes_progress_before_consuming(self):
        """Framstegsmarkören skrivs FÖRE konsumtionen.

        Kraschar konsumtionen (som LOGOUT-felen gjorde 2026-10-19) hämtas
        annars samma mail igen nästa körning — och minnesfotavtrycket
        upprepas utan att något nytt tillförs.
        """
        import inspect
        src = inspect.getsource(self.imap.action_poll_user)
        idx_write = src.find("'last_imap_sync'")
        idx_consume = src.find('_on_new_messages(')
        self.assertGreater(idx_write, -1)
        self.assertGreater(idx_consume, -1)
        self.assertLess(
            idx_write, idx_consume,
            'last_imap_sync ska skrivas innan _on_new_messages anropas')

    def test_poll_reports_logout_failures_in_finally(self):
        """LOGOUT-fel rapporteras i finally, även när poller kastar."""
        import inspect
        src = inspect.getsource(self.imap.action_poll_user)
        idx_finally = src.find('finally:')
        idx_report = src.find('_report_logout_failures')
        self.assertGreater(idx_finally, -1)
        self.assertGreater(
            idx_report, idx_finally,
            '_report_logout_failures ska anropas i finally-blocket')

    def test_logout_failures_distinct_messages_logged_separately(self):
        """Ett nytt, annorlunda fel får inte drunkna i det kända."""
        from odoo.addons.user_mail_imap.models import imap_server
        imap_server._LOGOUT_FAILURES.clear()
        for _ in range(5):
            imap_server._LOGOUT_FAILURES.append('LOGOUT => Return-Path: x')
        imap_server._LOGOUT_FAILURES.append('ConnectionResetError: boom')
        logger, handler, records, old_level = self._capture_logs(
            'odoo.addons.user_mail_imap.models.imap_server')
        try:
            imap_server._report_logout_failures('anna@example.com')
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
        self.assertEqual(len(records), 2)
        joined = '\n'.join(r.getMessage() for r in records)
        self.assertIn('x5', joined)
        self.assertIn('ConnectionResetError', joined)
        imap_server._LOGOUT_FAILURES.clear()

    # ── Spam: header-baserat filter (skip-spam-flagged-mail) ──

    @staticmethod
    def _spam_header_bytes(message_id, spam_lines, subject='Test'):
        """Header-block med godtyckliga spam-fält."""
        extra = ''.join('%s: %s\r\n' % (k, v) for k, v in spam_lines.items())
        return ('Message-ID: %s\r\nSubject: %s\r\nFrom: a@b.se\r\n'
                'Date: Mon, 05 Aug 2026 10:00:00 +0200\r\n%s\r\n'
                % (message_id, subject, extra)).encode()

    def test_spam_flagged_message_skipped(self):
        """X-Spam-Flag: YES hoppas över och når inte _on_new_messages."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 0
        user.last_imap_uidvalidity = '42'
        headers = {1: self._spam_header_bytes(
            '<spam1@example.com>', {'X-Spam-Flag': 'YES'})}
        fake = self._fake_conn([1], headers=headers,
                               bodies={1: self._body_bytes('<spam1@example.com>')})

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            n, _failed = self.env['user.mail.imap'].with_user(
                user).action_poll_user()

        self.assertEqual(n, 0, 'spam ska inte räknas som nytt mail')

    def test_spam_status_with_score_skipped(self):
        """X-Spam-Status: Yes, score=8.2 ... matchar (prefix)."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 0
        user.last_imap_uidvalidity = '42'
        headers = {1: self._spam_header_bytes(
            '<spam2@example.com>',
            {'X-Spam-Status': 'Yes, score=8.2 required=5.0 tests=BAYES_99'})}
        fake = self._fake_conn([1], headers=headers,
                               bodies={1: self._body_bytes('<spam2@example.com>')})

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            n, _failed = self.env['user.mail.imap'].with_user(
                user).action_poll_user()

        self.assertEqual(n, 0)

    def test_rspamd_header_skipped(self):
        """Rspamd: X-Spam: Yes matchar."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 0
        user.last_imap_uidvalidity = '42'
        headers = {1: self._spam_header_bytes(
            '<spam3@example.com>', {'X-Spam': 'Yes'})}
        fake = self._fake_conn([1], headers=headers,
                               bodies={1: self._body_bytes('<spam3@example.com>')})

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            n, _failed = self.env['user.mail.imap'].with_user(
                user).action_poll_user()

        self.assertEqual(n, 0)

    def test_unflagged_message_processed(self):
        """Mail utan spam-header går igenom som förut."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 0
        user.last_imap_uidvalidity = '42'
        headers = {1: self._spam_header_bytes(
            '<ham1@example.com>', {'X-Spam-Status': 'No, score=-2.1'})}
        fake = self._fake_conn([1], headers=headers,
                               bodies={1: self._body_bytes('<ham1@example.com>')})

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            n, _failed = self.env['user.mail.imap'].with_user(
                user).action_poll_user()

        self.assertEqual(n, 1, 'vanligt mail ska processas')

    def test_no_rules_means_no_filtering(self):
        """Tom regel-lista → allt behandlas som vanligt mail."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 0
        user.last_imap_uidvalidity = '42'
        self.env['ir.config_parameter'].sudo().set_param(
            'user_mail_imap.spam_headers', '[]')
        headers = {1: self._spam_header_bytes(
            '<spam4@example.com>', {'X-Spam-Flag': 'YES'})}
        fake = self._fake_conn([1], headers=headers,
                               bodies={1: self._body_bytes('<spam4@example.com>')})

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            n, _failed = self.env['user.mail.imap'].with_user(
                user).action_poll_user()

        self.assertEqual(n, 1, 'utan regler ska inget filtreras')

    def test_spam_no_body_fetch(self):
        """Spam får aldrig ett BODY.PEEK[]-anrop."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 0
        user.last_imap_uidvalidity = '42'
        headers = {1: self._spam_header_bytes(
            '<spam5@example.com>', {'X-Spam-Flag': 'YES'})}
        fake = self._fake_conn([1], headers=headers,
                               bodies={1: self._body_bytes('<spam5@example.com>')})

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(user).action_poll_user()

        body_fetches = [
            c for c in fake.uid.call_args_list
            if c[0][0] == 'FETCH' and 'HEADER.FIELDS' not in c[0][2]]
        self.assertFalse(body_fetches,
                         'spam ska avgöras före body-fetch')

    def test_spam_advances_cursor(self):
        """Cursorn går förbi spam-mailet."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 0
        user.last_imap_uidvalidity = '42'
        headers = {9: self._spam_header_bytes(
            '<spam6@example.com>', {'X-Spam-Flag': 'YES'})}
        fake = self._fake_conn([9], headers=headers,
                               bodies={9: self._body_bytes('<spam6@example.com>')})

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(user).action_poll_user()

        user.invalidate_recordset()
        self.assertEqual(user.last_imap_uid, 9,
                         'cursorn ska avancera förbi spam')

    def test_spam_not_counted_as_parse_error(self):
        """Spam-överhopp får inte öka parse_errors_24h."""
        from unittest.mock import patch
        # _poll_health() söker via ORM, som filtrerar bort __system__ —
        # använd en riktig användare så sökningen hittar den.
        user = self.env['res.users'].create({
            'name': 'Spam Health User',
            'login': 'spam-health@vertel.se',
            'password': 'x',
        })
        user.imap_password = user._encrypt_imap_pw('x')
        user.imap_poll_enabled = True
        user.postfix_mail = 'spam-health@vertel.se'
        user.last_imap_sync = False
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE res_users SET imap_poll_enabled = true WHERE id = %s",
            (user.id,))
        self.env.invalidate_all()
        user.last_imap_uid = 0
        user.last_imap_uidvalidity = '42'
        headers = {1: self._spam_header_bytes(
            '<spam7@example.com>', {'X-Spam-Flag': 'YES'})}
        fake = self._fake_conn([1], headers=headers,
                               bodies={1: self._body_bytes('<spam7@example.com>')})

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(user).action_poll_user()

        health = self.env['user.mail.poll']._poll_health()
        self.assertIn(user.login, health)
        self.assertEqual(health[user.login]['parse_errors_24h'], 0,
                         'spam är inte ett parse-fel')
        self.assertEqual(health[user.login]['spam_skipped_24h'], 1)

    def test_broken_rule_json_is_safe(self):
        """Trasig JSON ger tom lista — ingen krasch."""
        self.env['ir.config_parameter'].sudo().set_param(
            'user_mail_imap.spam_headers', '{inte json')
        rules = self.env['user.mail.imap']._spam_rules()
        self.assertEqual(rules, [])

    def test_spam_never_modifies_mailbox(self):
        """Spam-vägen får aldrig anropa STORE/COPY/MOVE/EXPUNGE."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 0
        user.last_imap_uidvalidity = '42'
        headers = {1: self._spam_header_bytes(
            '<spam8@example.com>', {'X-Spam-Flag': 'YES'})}
        fake = self._fake_conn([1], headers=headers,
                               bodies={1: self._body_bytes('<spam8@example.com>')})

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(user).action_poll_user()

        forbidden = [
            c for c in fake.uid.call_args_list
            if c[0][0] in ('STORE', 'COPY', 'MOVE', 'EXPUNGE')]
        self.assertFalse(forbidden, 'pollern får inte ändra brevlådan')
        self.assertFalse(fake.store.called)
        self.assertFalse(fake.expunge.called)

    def test_uidvalidity_read_from_response_not_select(self):
        """UIDVALIDITY ska läsas med response(), inte ur select()-svaret.

        imaplib.select() returnerar bara EXISTS. Den tidigare koden letade
        efter "UIDVALIDITY nnn" i det svaret, hittade aldrig något och
        returnerade alltid None — så resync-detekteringen kunde aldrig slå
        till.
        """
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 500
        user.last_imap_uidvalidity = False
        self.env.flush_all()
        fake = self._fake_conn([], uidvalidity='777')

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(user).action_poll_user()

        user.invalidate_recordset()
        self.assertEqual(user.last_imap_uidvalidity, '777',
                         'UIDVALIDITY ska sparas från response()')
        self.assertTrue(fake.response.called,
                        'koden ska anropa response("UIDVALIDITY")')

    def test_uidvalidity_missing_does_not_crash(self):
        """Saknat UIDVALIDITY-svar ska ge None, inte krasch."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 500
        self.env.flush_all()
        fake = self._fake_conn([])
        fake.response.return_value = ('UIDVALIDITY', [])

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(user).action_poll_user()

        user.invalidate_recordset()
        self.assertFalse(user.last_imap_uidvalidity,
                         'tomt svar ska lämna fältet tomt')

    def test_uidvalidity_change_triggers_resync(self):
        """Bytet ska nollställa cursorn och söka ALL."""
        from unittest.mock import patch
        user = self._poll_user()
        user.last_imap_uid = 500
        user.last_imap_uidvalidity = 'OLD'
        self.env.flush_all()
        fake = self._fake_conn([], uidvalidity='NEW')

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(user).action_poll_user()

        user.invalidate_recordset()
        self.assertEqual(user.last_imap_uidvalidity, 'NEW')
        search_args = [c for c in fake.uid.call_args_list
                       if c[0][0] == 'SEARCH']
        self.assertIn('ALL', str(search_args[0][0]),
                      'resync ska söka ALL, inte UID 501:*')

    # ── Mapplistning: batchning + cache (batch-imap-folder-listing) ──

    def _fake_list_conn(self, uids, response_order=None, omit=None):
        """IMAP-dubbel för action_fetch_mails.

        `response_order` låter servern svara i en annan ordning än den
        efterfrågade, `omit` hoppar över ett UID i svaret.
        """
        from unittest.mock import MagicMock
        fake = MagicMock()
        fake.select.return_value = ('OK', [str(len(uids)).encode()])
        fake.login.return_value = ('OK', [b'logged in'])
        fake.search.return_value = (
            'OK', [b' '.join(str(u).encode() for u in uids)])

        def _uid(cmd, *args):
            if cmd != 'FETCH':
                return ('OK', [b''])
            uid_set = args[0]
            ids = [int(x) for x in str(uid_set).split(',') if str(x).strip()]
            if response_order:
                ids = [u for u in response_order if u in ids]
            out = []
            for u in ids:
                if omit and u == omit:
                    continue
                hdr = self._header_bytes('<m%d@example.com>' % u).replace(
                    b'\r\n\r\n', b'\r\n\r\n')
                out.append((b'%d (UID %d FLAGS (\\Seen) BODY[HEADER] {1}'
                            % (u, u), hdr))
            return ('OK', out)
        fake.uid.side_effect = _uid
        return fake

    def _list_user(self):
        """Testanvändare med postfix_mail + IMAP-lösenord (krävs av connect)."""
        self.user.imap_password = self.user._encrypt_imap_pw('x')
        self.user.postfix_mail = 'list-test@vertel.se'
        return self.user

    def _clear_page_cache(self):
        from odoo.addons.user_mail_imap.models.imap_server import _mail_cache
        _mail_cache.clear()

    def test_fetch_mails_batches_single_command(self):
        """80 UID:n ska hämtas med ETT FETCH."""
        from unittest.mock import patch
        self._clear_page_cache()
        uids = list(range(1, 81))
        fake = self._fake_list_conn(uids)

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            res = self.env['user.mail.imap'].with_user(self._list_user()).action_fetch_mails('INBOX')

        fetches = [c for c in fake.uid.call_args_list if c[0][0] == 'FETCH']
        self.assertEqual(len(fetches), 1,
                         'en sida på 80 ska vara ett FETCH, inte 80')
        self.assertEqual(res['total'], 80)
        self.assertEqual(len(res['messages']), 80)

    def test_fetch_mails_splits_large_page(self):
        """250 UID:n ska delas i två FETCH (UID_BATCH_SIZE=200)."""
        from unittest.mock import patch
        self._clear_page_cache()
        uids = list(range(1, 251))
        fake = self._fake_list_conn(uids)

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(self._list_user()).action_fetch_mails(
                'INBOX', offset=0, limit=250)

        fetches = [c for c in fake.uid.call_args_list if c[0][0] == 'FETCH']
        self.assertEqual(len(fetches), 2,
                         '250 UID:n ska delas i två batcher')

    def test_fetch_mails_preserves_newest_first(self):
        """Ordningen nyaste-först gäller även om servern svarar baklänges."""
        from unittest.mock import patch
        self._clear_page_cache()
        uids = [1, 2, 3, 4, 5]
        fake = self._fake_list_conn(uids, response_order=[1, 2, 3, 4, 5])

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            res = self.env['user.mail.imap'].with_user(self._list_user()).action_fetch_mails('INBOX')

        got = [m['uid'] for m in res['messages']]
        self.assertEqual(got, [5, 4, 3, 2, 1],
                         'nyaste först, oavsett svarsordning')

    def test_fetch_mails_missing_uid_keeps_order(self):
        """Ett UID servern inte svarar på stör inte restens ordning."""
        from unittest.mock import patch
        self._clear_page_cache()
        uids = [1, 2, 3, 4, 5]
        fake = self._fake_list_conn(uids, omit=3)

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            res = self.env['user.mail.imap'].with_user(self._list_user()).action_fetch_mails('INBOX')

        got = [m['uid'] for m in res['messages']]
        self.assertEqual(got, [5, 4, 2, 1],
                         'det saknade UID:et hoppas över, resten behåller ordningen')

    def test_fetch_mails_second_call_uses_cache(self):
        """Andra anropet för samma sida ska inte öppna en anslutning."""
        from unittest.mock import patch
        self._clear_page_cache()
        uids = [1, 2, 3]
        fake = self._fake_list_conn(uids)

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(self._list_user()).action_fetch_mails('INBOX')
            calls_after_first = fake.uid.call_count
            self.env['user.mail.imap'].with_user(self._list_user()).action_fetch_mails('INBOX')
            self.assertEqual(fake.uid.call_count, calls_after_first,
                             'andra anropet ska serveras ur cachen')

    def test_fetch_mails_pages_do_not_collide(self):
        """Sida 1 och sida 2 ska cachas separat."""
        from unittest.mock import patch
        self._clear_page_cache()
        uids = list(range(1, 11))
        fake = self._fake_list_conn(uids)

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            p1 = self.env['user.mail.imap'].with_user(self._list_user()).action_fetch_mails(
                'INBOX', offset=0, limit=3)
            p2 = self.env['user.mail.imap'].with_user(self._list_user()).action_fetch_mails(
                'INBOX', offset=3, limit=3)

        self.assertEqual([m['uid'] for m in p1['messages']], [10, 9, 8])
        self.assertEqual([m['uid'] for m in p2['messages']], [7, 6, 5],
                         'sida 2 får inte servera sida 1:s innehåll')

    def test_fetch_mails_failure_not_cached(self):
        """Ett anslutningsfel ska inte lämna en cache-post."""
        from unittest.mock import patch
        from odoo.addons.user_mail_imap.models.imap_server import _mail_cache
        self._clear_page_cache()
        before = len(_mail_cache)

        with patch('imaplib.IMAP4_SSL',
                   side_effect=OSError('connection refused')):
            with self.assertRaises(OSError):
                self.env['user.mail.imap'].with_user(self._list_user()).action_fetch_mails('INBOX')

        self.assertEqual(len(_mail_cache), before,
                         'ett fel ska aldrig cachas')

    def test_flag_change_invalidates_page_cache(self):
        """Flaggbyte ska rensa mappens sid-cache."""
        from unittest.mock import patch
        from odoo.addons.user_mail_imap.models.imap_server import _mail_cache
        self._clear_page_cache()
        uids = [1, 2, 3]
        fake = self._fake_list_conn(uids)

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(self._list_user()).action_fetch_mails('INBOX')
            self.assertTrue(
                [k for k in _mail_cache if k.startswith('page:')],
                'sidan ska vara cachad')
            self.env['user.mail.imap'].with_user(self._list_user()).action_set_flag(
                'INBOX', [1], 'seen', True)

        self.assertFalse(
            [k for k in _mail_cache if k.startswith('page:')],
            'flaggbytet ska ha rensat sid-cachen')

    def test_move_invalidates_source_folder_cache(self):
        """Flytt ska rensa både käll- och målmappens cache."""
        from unittest.mock import patch
        from odoo.addons.user_mail_imap.models.imap_server import _mail_cache
        self._clear_page_cache()
        uids = [1, 2, 3]
        fake = self._fake_list_conn(uids)

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(self._list_user()).action_fetch_mails('INBOX')
            self.env['user.mail.imap'].with_user(self._list_user()).action_move('INBOX', [1], 'Archive')

        self.assertFalse(
            [k for k in _mail_cache if k.startswith('page:')],
            'flytten ska ha rensat källmappens cache')

    def test_new_mail_invalidates_page_cache(self):
        """Pollerns ingest ska rensa INBOX-cachen."""
        from unittest.mock import patch
        from odoo.addons.user_mail_imap.models.imap_server import _mail_cache
        self._clear_page_cache()
        uids = [1, 2, 3]
        fake = self._fake_list_conn(uids)

        with patch('imaplib.IMAP4_SSL', return_value=fake):
            self.env['user.mail.imap'].with_user(self._list_user()).action_fetch_mails('INBOX')

        self.assertTrue([k for k in _mail_cache if k.startswith('page:')])
        # Pollerns väg rensar INBOX-cachen efter _on_new_messages.
        from odoo.addons.user_mail_imap.models.imap_server import (
            _invalidate_folder_cache)
        _invalidate_folder_cache(self.env.user.id, 'INBOX')
        self.assertFalse(
            [k for k in _mail_cache if k.startswith('page:')],
            'pollerns ingest ska rensa sid-cachen')
