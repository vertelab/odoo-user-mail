# -*- coding: utf-8 -*-
"""Rök-test för user_mail_common — versionsagnostiskt.

Porterings-DoD kräver minst ett test per modul som saknade tester:
(a) skapa en post i modulens huvudmodell, (b) öppna dess huvudvy, eller
(c) anropa dess huvudmetod. Här är huvudmodellen sieve.script och
huvudmetoden sieve.compiler.assemble().
"""

from odoo.tests.common import TransactionCase


class TestSieveScript(TransactionCase):

    def test_create_script_for_user(self):
        """En post i sieve.script ska gå att skapa och läsas tillbaka."""
        script = self.env['sieve.script'].create({
            'user_id': self.env.user.id,
            'name': 'odoo_ai',
            'body': 'keep;\n',
        })
        self.assertTrue(script.id)
        self.assertEqual(script.user_id, self.env.user)
        self.assertEqual(script.state, 'draft')
        self.assertTrue(script.active)

    def test_compiler_produces_valid_keep(self):
        """Utan delar ska kompilatorn ge ett minimalt, giltigt script."""
        compiler = self.env['sieve.compiler']
        self.assertEqual(compiler.assemble([]), 'keep;\n')

    def test_compiler_quotes_newlines(self):
        """Newlines i en quoted string gör scriptet ogiltigt — de ska
        ersättas med mellanslag."""
        quoted = self.env['sieve.compiler'].quote('rad ett\nrad två')
        self.assertNotIn('\n', quoted)
        self.assertTrue(quoted.startswith('"') and quoted.endswith('"'))
