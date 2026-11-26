# -*- coding: utf-8 -*-
"""Rök-test för user_scim — versionsagnostiskt."""

from odoo.tests.common import TransactionCase


class TestScim(TransactionCase):

    def test_scim_fields_exist(self):
        """res.users bär SCIM-fälten."""
        fields = self.env['res.users']._fields
        for name in ('scim_id', 'scim_last_sync', 'scim_sync_error'):
            self.assertIn(name, fields)

    def test_scim_id_is_char(self):
        self.assertEqual(self.env['res.users']._fields['scim_id'].type,
                         'char')
