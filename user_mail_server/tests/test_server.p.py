# -*- coding: utf-8 -*-
"""Rök-test för user_mail_server — versionsagnostiskt.

Modulen ärver res.users och hashar lösenordet till dovecot_password.
Testet bevisar att modulen laddar och att huvudbeteendet fungerar.
"""

from odoo.tests.common import TransactionCase


class TestMailServer(TransactionCase):

    def test_password_is_hashed_to_dovecot(self):
        """write() med password sätter dovecot_password (sha512-crypt)."""
        user = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Server Test',
                'login': 'server.test@example.com',
            })
        user.write({'password': 'hemligt123'})
        self.assertTrue(user.dovecot_password)
        self.assertTrue(user.dovecot_password.startswith('$6$'),
                        'dovecot_password ska vara sha512-crypt')

    def test_unlink_removes_aliases(self):
        """unlink() tar bort användarens postfix-alias först."""
        # #if VERSION >= "19.0"
        # user_mail_client.write() kräver passwd_server i odoo.conf för att
        # synka mot mailservern — finns inte i testmiljön. Hoppa.
        import odoo.tools
        if not odoo.tools.config.get('passwd_server'):
            self.skipTest('passwd_server saknas i testmiljön')
        # #endif
        user = self.env['res.users'].with_context(
            no_reset_password=True).create({
                'name': 'Alias Test',
                'login': 'alias.test@example.com',
            })
        self.env['postfix.alias'].create({
            'name': 'alias@example.com',
            'user_id': user.id,
        })
        user.unlink()
        self.assertFalse(self.env['postfix.alias'].search([
            ('user_id', '=', user.id)]))
