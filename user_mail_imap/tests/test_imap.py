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
        self.assertTrue(self.imap, "user.mail.imap model should exist")
        self.assertEqual(self.imap._description, 'IMAP Mail Operations')

    def test_model_fields(self):
        user_fields = self.env['res.users'].fields_get()
        self.assertIn('imap_password', user_fields, "res.users should have imap_password field")
