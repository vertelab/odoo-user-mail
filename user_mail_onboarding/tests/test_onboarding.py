# -*- coding: utf-8 -*-
"""Rök-test för user_mail_onboarding — versionsagnostiskt.

Modulen skapar en slide.channel med fem lektioner (data-XML).
"""

from odoo.tests.common import TransactionCase


class TestOnboarding(TransactionCase):

    def test_channel_exists(self):
        """Onboardingskanalen skapas av data-XML."""
        channel = self.env['slide.channel'].search([
            ('name', 'ilike', 'e-post')], limit=1)
        self.assertTrue(channel, 'onboardingskanalen saknas')
        self.assertGreaterEqual(len(channel.slide_ids), 1,
                                'kanalen ska ha minst en lektion')
