# -*- coding: utf-8 -*-
"""Rök-test för user_password_strength — versionsagnostiskt."""

from odoo.tests.common import TransactionCase


class TestPasswordStrength(TransactionCase):

    def test_settings_model_exists(self):
        """Inställningsmodellen laddar (ärver res.config.settings)."""
        self.assertIn('res.config.settings', self.env)
        self.assertTrue(self.env['res.config.settings'])
