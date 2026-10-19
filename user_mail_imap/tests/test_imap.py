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
        fake.select.return_value = ('OK', [b'1', b'UIDVALIDITY 42'])
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
            n = self.env['user.mail.imap'].with_user(self.user).action_poll_user()

        self.assertEqual(n, 1, 'ett nytt mail ska pollas')
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
        self.user.imap_password = False
        self.env.cr.execute(
            "UPDATE res_users SET imap_poll_enabled = true, "
            "imap_password = NULL WHERE id = %s", (self.user.id,))
        self.user.invalidate_recordset()
        with patch('imaplib.IMAP4_SSL') as m:
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
        fake.select.return_value = (
            'OK', [str(len(uids)).encode(),
                   ('UIDVALIDITY %s' % uidvalidity).encode()])
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
            n = self.env['user.mail.imap'].with_user(user).action_poll_user()

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
            n = self.env['user.mail.imap'].with_user(user).action_poll_user()

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
