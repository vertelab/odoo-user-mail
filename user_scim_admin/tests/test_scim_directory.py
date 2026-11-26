# -*- coding: utf-8 -*-
"""Rök-test för user_scim_admin — versionsagnostiskt."""

from odoo.tests.common import TransactionCase


class TestScimDirectory(TransactionCase):

    def test_model_exists(self):
        self.assertEqual(self.env['scim.directory.user']._name,
                         'scim.directory.user')

    def test_create_directory_row(self):
        """En katalograd ska gå att skapa och läsas tillbaka."""
        row = self.env['scim.directory.user'].create({
            'user_name': 'kalle',
            'display_name': 'Kalle Test',
            'email_primary': 'kalle@example.com',
        })
        self.assertTrue(row.id)
        self.assertEqual(row.user_name, 'kalle')
