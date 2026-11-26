# -*- coding: utf-8 -*-
"""Rök-test för user_password_tmp — versionsagnostiskt."""

from odoo.tests.common import TransactionCase


class TestPasswordTmp(TransactionCase):

    def test_model_exists(self):
        self.assertEqual(
            self.env['res.users.password']._name, 'res.users.password')

    def test_passwd_tmp_field(self):
        """res.users bär passwd_tmp (tillfälligt lösenord)."""
        self.assertIn('passwd_tmp', self.env['res.users']._fields)
