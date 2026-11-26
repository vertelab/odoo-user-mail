# -*- coding: utf-8 -*-
"""Rök-test för user_scim_matrix — versionsagnostiskt.

Modulen är uninstallable utan user_matrix; testet bevisar att den laddar
när beroendet finns.
"""

from odoo.tests.common import TransactionCase


class TestScimMatrix(TransactionCase):

    def test_matrix_field_exists(self):
        """res.users bär matrix_id när modulen laddar."""
        self.assertIn('matrix_id', self.env['res.users']._fields)
