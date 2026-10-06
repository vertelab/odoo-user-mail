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
