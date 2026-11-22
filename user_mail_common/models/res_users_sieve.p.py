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

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ── Script ───────────────────────────────────────────────────────────

    sieve_script_state = fields.Selection(
        related='sieve_script_id.state', string='Sieve-status',
        readonly=True)
    sieve_script_error = fields.Text(
        related='sieve_script_id.last_error', string='Sieve-fel',
        readonly=True)
    sieve_script_id = fields.Many2one(
        'sieve.script', string='Sieve-script', readonly=True,
        compute='_compute_sieve_script_id', store=True)

    def _compute_sieve_script_id(self):
        """Länk till användarens script, för statusfälten i vyn.

        Lagras (store=True) därför att related-fälten nedan hänger på det:
        ett icke-lagrat fält kan inte vara beroende för ett annat, eftersom
        ORM:en inte kan avgöra vilka användare som ska räknas om när
        scriptet ändras.

        Beror INTE på något fält på res.users — det finns inget att hänga
        det på, eftersom scriptet skapas lat. Det räknas därför om vid
        behov; sieve.script.action_sync() anropar _sieve_refresh_user()
        när statusen ändras.
        """
        scripts = self.env['sieve.script'].search([
            ('user_id', 'in', self.ids)])
        by_user = {s.user_id.id: s for s in scripts}
        for user in self:
            user.sieve_script_id = by_user.get(user.id)

    def _sieve_refresh_user(self):
        """Räkna om sieve_script_id efter att scriptets status ändrats."""
        self.invalidate_recordset(['sieve_script_id'])

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

    # ── Navigering ───────────────────────────────────────────────────────

    def action_open_sieve_script(self):
        """Öppna det genererade Sieve-scriptet för inloggad användare.

        Ersätter den tidigare menyposten "Serverregler (Sieve)". Vyn är
        ingen regellista — den är scriptet med synkstatus och senaste fel —
        och hör därför på inställningssidan, inte i menyn bredvid
        E-postregler.

        Skapar scriptet om det saknas, så knappen alltid leder någonstans
        och statusen alltid går att inspektera (även innan första regeln).
        """
        self.ensure_one()
        script = self._sieve_script(create=True)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sieve-status'),
            'res_model': 'sieve.script',
            'res_id': script.id,
            'view_mode': 'form',
            'target': 'current',
        }
