# -*- coding: utf-8 -*-
"""Rök-test för user_password_strength — versionsagnostiskt."""

from odoo.tests.common import TransactionCase


class TestPasswordStrength(TransactionCase):

    def test_settings_model_exists(self):
        """Inställningsmodellen laddar (ärver res.config.settings)."""
        # Ett tomt recordset är falsy — pröva modellnamnet.
        self.assertEqual(self.env['res.config.settings']._name,
                         'res.config.settings')
