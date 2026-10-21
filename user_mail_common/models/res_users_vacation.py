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
"""res.users — vacation till Sieve.

VARFÖR CRON OCH INTE DATUMVILLKOR I SIEVE
=========================================

Sieve har `currentdate`, men `:value "ge"` kräver `require ["relational"]`
och ger ett script som ändå måste städas bort efter perioden. Ett dagligt
cron är enklare och har EN sanning: `vacation_active` + datumen.

Verifierat mot imap.vertel.se:4190:
  - `currentdate :value "ge" "date" "..."` UTAN relational  -> avvisas
  - samma MED require ["relational"]                        -> OK
  - `vacation :days 7 :from "..." :subject "..." "..."`     -> OK

Vi väljer cron. Datumlogiken ligger då i Python där den kan testas.
"""

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# Fält som påverkar vacation-blocket. Ändras något av dem ska scriptet
# byggas om direkt — användaren ska inte behöva vänta till nästa natt.
VACATION_FIELDS = {
    'vacation_active', 'vacation_subject', 'vacation_text',
    'vacation_from', 'vacation_to',
    # postfix_mail är :from-adressen. Byts den måste autosvaret byta
    # avsändare också.
    'postfix_mail', 'login', 'postfix_active',
}


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ── Datumlogik ───────────────────────────────────────────────────────

    def _vacation_in_range(self, today=None):
        """Är vacation aktiv IDAG enligt from/to?

        Tomma datum betyder "öppet intervall": bara `vacation_from` satt =
        från och med det datumet och framåt. Bara `vacation_to` = fram till
        och med det datumet. Båda tomma = alltid (när active är satt).
        """
        self.ensure_one()
        if not self.vacation_active:
            return False
        today = today or fields.Date.context_today(self)
        if self.vacation_from and self.vacation_from > today:
            return False
        if self.vacation_to and self.vacation_to < today:
            return False
        return True

    # ── Bygg och synka ───────────────────────────────────────────────────

    def _sieve_vacation_part(self, today=None):
        """(kod, extensions) för vacation-delen."""
        self.ensure_one()
        if not self._vacation_in_range(today):
            return None, []
        return self.env['sieve.compiler'].vacation_block(self)

    def _sieve_rules_part(self):
        """(kod, extensions) för användarens server-regler.

        Reglerna ägs av `user_mail_ai.rule`. Modulen beror på
        user_mail_common, inte tvärtom — så vi letar efter modellen i
        stället för att importera den. Saknas user_mail_ai (ren
        klient-installation) finns inga regler och vacation fungerar ändå.
        """
        self.ensure_one()
        if 'user_mail_ai.rule' not in self.env:
            return None, []
        rules = self.env['user_mail_ai.rule'].search([
            ('user_id', '=', self.id),
            ('enforcement', '=', 'server'),
            ('active', '=', True),
        ])
        return self.env['sieve.compiler'].rules_part(rules)

    def _sieve_rebuild(self, today=None):
        """Bygg om scriptet från vacation + regler och synka.

        Detta är den ENDA vägen till `sieve.script.body` — aldrig patchning.
        Idempotent: samma indata ger samma utdata, så en omsynk utan
        ändringar rör inte servern i onödan.
        """
        compiler = self.env['sieve.compiler']
        parts = [
            self._sieve_vacation_part(today),
            self._sieve_rules_part(),
        ]
        body = compiler.assemble(parts)
        return self._sieve_write_body(body)

    def _sieve_sync_vacation(self):
        """Bekvämlighet: bygg om och synka (tyst)."""
        return self._sieve_rebuild()

    # ── Hook: spara ska slå igenom direkt ────────────────────────────────

    def write(self, values):
        res = super().write(values)
        if VACATION_FIELDS & set(values):
            for user in self:
                try:
                    user._sieve_rebuild()
                except Exception as e:
                    # Ett trasigt Sieve-script får ALDRIG rulla tillbaka
                    # användarens sparande. Felet hamnar i sieve.script
                    # (state=error, last_error) och syns i UI:t.
                    _logger.warning(
                        'Sieve-omsynk efter sparande misslyckades för %s: %s',
                        user.name, e)
        return res

    # ── Cron ─────────────────────────────────────────────────────────────

    @api.model
    def _cron_sieve_vacation(self):
        """Daglig: slå på/av vacation enligt from/to.

        Kör för ALLA användare med vacation_active satt, plus de som har
        ett script som INNEHÅLLER vacation men inte längre ska ha det
        (annars blir ett utgånget autosvar kvar på servern).
        """
        today = fields.Date.context_today(self)
        candidates = self.search([
            '|',
            ('vacation_active', '=', True),
            ('id', 'in', self._users_with_vacation_in_script()),
        ])
        done = 0
        for user in candidates:
            try:
                user._sieve_rebuild(today=today)
                done += 1
            except Exception as e:
                _logger.warning(
                    'Sieve vacation-cron misslyckades för %s: %s',
                    user.name, e)
        _logger.info('Sieve vacation-cron: %d användare behandlade', done)
        return done

    @api.model
    def _users_with_vacation_in_script(self):
        """Id:n för användare vars genererade script innehåller vacation.

        Behövs för att städa bort ett autosvar vars period gått ut medan
        `vacation_active` redan slagits av — annars ligger blocket kvar.
        """
        scripts = self.env['sieve.script'].search([
            ('body', 'ilike', 'vacation'),
        ])
        return scripts.mapped('user_id').ids
