# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
"""res.users — Sieve-hjälpmetoder.

Här ligger bara det som hör till användaren som SUBJEKT: vilket script
den äger, och hur man begär en omsynk. Själva kompileringen av regler
och vacation görs av anroparen (user_mail_ai respektive user_mail_client)
eftersom de äger sina respektive fält.
"""

import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ── Script ───────────────────────────────────────────────────────────

    def _sieve_script(self, create=True):
        """Användarens Odoo-ägda script (skapat vid behov)."""
        self.ensure_one()
        return self.env['sieve.script']._get_for_user(self, create=create)

    def _sieve_script_body(self):
        """Nuvarande genererade kropp ('' om inget script finns)."""
        self.ensure_one()
        script = self._sieve_script(create=False)
        return script.body or '' if script else ''

    def _sieve_write_body(self, body):
        """Sätt kroppen och synka till servern.

        Tyst synk: fel hamnar i `last_error`, inte som undantag. Anropas
        från cron och från write-hooks — ett kastat fel där skulle rulla
        tillbaka användarens sparande.
        """
        self.ensure_one()
        script = self._sieve_script()
        script.write({'body': body})
        script.action_sync()
        return script

    # ── Lösenord ─────────────────────────────────────────────────────────
    #
    # `_sieve_password()` ligger i res_users_password.py, tillsammans med
    # fältet `sieve_password` och den write()-hook som fångar klartexten.
    # Att ha den där och inte här håller lösenordshanteringen på ett ställe.
