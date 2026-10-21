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
"""sieve.script — det genererade Sieve-scriptet, ett per användare.

Varför en egen modell och inte fält på res.users:

  - `body` är HÄRLEDD data (regler + vacation kompileras ihop). Den hör
    inte i användartabellen.
  - Synkstatus och feltext behöver egen livscykel: ett misslyckat
    putscript ska synas utan att man öppnar en användarform.
  - En användare kan i framtiden ha flera script (t.ex. ett experiment).
    Unikheten är per (user_id, name), inte per user_id.

VIKTIGT om namn: Odoo äger ENDAST scriptet som heter `odoo_ai`. En
användares handskrivna script (t.ex. `arkiv`) läses aldrig och skrivs
aldrig över — se `_own_script_names()`.
"""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

SCRIPT_NAME = 'odoo_ai'


class SieveScript(models.Model):
    _name = 'sieve.script'
    _description = 'Genererat Sieve-script'
    _order = 'user_id, name'

    user_id = fields.Many2one(
        'res.users', string='Användare', required=True, ondelete='cascade',
        index=True)
    name = fields.Char(
        'Script-namn', required=True, default=SCRIPT_NAME,
        help='Namnet i ManageSieve. Odoo äger bara scriptet "odoo_ai".')
    body = fields.Text(
        'Genererad Sieve',
        help='Det som faktiskt laddas upp till servern. Härleds alltid '
             'från regler och vacation — redigeras inte för hand.')
    state = fields.Selection([
        ('draft', 'Inte synkad'),
        ('synced', 'Synkad'),
        ('error', 'Fel'),
    ], string='Status', default='draft', required=True, readonly=True)
    last_sync = fields.Datetime('Senast synkad', readonly=True)
    last_error = fields.Text('Senaste fel', readonly=True)
    active = fields.Boolean('Aktiv', default=True)
    is_active_on_server = fields.Boolean(
        'Aktiv på servern', readonly=True,
        help='True när detta script är användarens aktiva script i Dovecot.')

    _sql_constraints = [
        ('unique_user_script', 'unique(user_id, name)',
         'Användaren kan bara ha ett script med detta namn!'),
    ]

    # ── Hämta/skapa ──────────────────────────────────────────────────────

    @api.model
    def _get_for_user(self, user, name=SCRIPT_NAME, create=True):
        """Användarens script, skapat vid behov."""
        script = self.search([('user_id', '=', user.id), ('name', '=', name)],
                             limit=1)
        if not script and create:
            script = self.create({'user_id': user.id, 'name': name})
            # Sätt länken direkt. res.users.sieve_script_id är lagrad men
            # har inget fältberoende att räkna om på (scriptet skapas lat),
            # så utan detta skulle statusfälten i användarformuläret vara
            # tomma ända till nästa gång posten rörs — och då syns ingen
            # varning när synken fallerar.
            #
            # Skrivs med SQL och inte user.write(): den senare går genom
            # user_mail_client.write() som kräver passwd_server i
            # odoo.conf. Ett internt fält ska inte tvinga fram en
            # LDAP-synk av användaren.
            self.env.cr.execute(
                'UPDATE res_users SET sieve_script_id = %s WHERE id = %s',
                (script.id, user.id))
            user.invalidate_recordset(['sieve_script_id'])
        return script

    # ── Validering ───────────────────────────────────────────────────────

    def _validate(self):
        """Validera scriptet lokalt OCH på servern.

        Två steg, båda krävs:
          1. sievelib.parser — snabb lokal syntaxkontroll, fångar trasig
             generering (t.ex. felciterat mappnamn) innan vi rör servern.
          2. CHECKSCRIPT — serverns egen kompilering. Det är den som
             avgör; parsern accepterar saker Pigeonhole avvisar.

        Kastar UserError med serverns feltext. En trasig AKTIV regel får
        Dovecot att avvisa eller felsortera post — därför är detta ingen
        varning utan ett hårt stopp.
        """
        self.ensure_one()
        body = self.body or ''
        if not body.strip():
            raise UserError(_('Sieve-scriptet är tomt — inget att ladda upp.'))

        # 1. Lokal parse
        try:
            from sievelib.parser import Parser
        except ImportError:
            raise UserError(_('Python-paketet sievelib saknas.'))
        if not Parser().parse(body):
            raise UserError(_(
                'Det genererade Sieve-scriptet kunde inte parsas lokalt. '
                'Detta är en bugg i kompilatorn, inte i användarens regler.'))

        # 2. Server-side kompilering
        client = self.env['sieve.client']
        conn = client._connect(self.user_id)
        try:
            if not client._checkscript(conn, body):
                raise UserError(_(
                    'Servern avvisade Sieve-scriptet: %s',
                    client._server_error(conn) or _('okänt fel')))
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        return True

    # ── Synk ─────────────────────────────────────────────────────────────

    def action_sync(self):
        """Ladda upp och aktivera scriptet.

        Kastar ALDRIG vidare till cron: fel fångas och sparas i
        `last_error` så att UI:t kan visa dem. Den som anropar från en
        knapp får felet via `_raise_on_error()`.
        """
        client = self.env['sieve.client']
        for script in self:
            try:
                script._sync_one(client)
            except Exception as e:
                _logger.warning('Sieve-sync misslyckades för %s: %s',
                                script.user_id.name, e)
                script.write({
                    'state': 'error',
                    'last_error': str(e),
                })
            finally:
                # Statusfälten på res.users är related till det här
                # scriptet. Utan invalidering visar användarformuläret
                # kvarvarande state tills något annat rör posten — och
                # varningsbannern skulle aldrig dyka upp.
                script.user_id.invalidate_recordset(
                    ['sieve_script_id', 'sieve_script_state',
                     'sieve_script_error'])
        return True

    def _sync_one(self, client):
        self.ensure_one()
        self._validate()

        conn = client._connect(self.user_id)
        try:
            client._putscript(conn, self.name, self.body)
            client._setactive(conn, self.name)
            active_name, _others = client._listscripts(conn)
        finally:
            try:
                conn.logout()
            except Exception:
                pass

        self.write({
            'state': 'synced',
            'last_sync': fields.Datetime.now(),
            'last_error': False,
            'is_active_on_server': active_name == self.name,
        })
        return True

    def action_sync_raise(self):
        """Synka och kasta vidare felet — för knappar i UI:t.

        Cron använder action_sync (tyst), en användare som trycker på
        "Synka" ska få veta om det gick fel.
        """
        self.ensure_one()
        self._validate()
        client = self.env['sieve.client']
        conn = client._connect(self.user_id)
        try:
            client._putscript(conn, self.name, self.body)
            client._setactive(conn, self.name)
            active_name, _others = client._listscripts(conn)
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        self.write({
            'state': 'synced',
            'last_sync': fields.Datetime.now(),
            'last_error': False,
            'is_active_on_server': active_name == self.name,
        })
        return True

    def action_pull_from_server(self):
        """Läs serverns version av Odoo-ägda script (diagnostik).

        Läser bara `odoo_ai`. Handskrivna script rörs aldrig.
        """
        self.ensure_one()
        client = self.env['sieve.client']
        conn = client._connect(self.user_id)
        try:
            body = client._getscript(conn, self.name)
            active_name, _others = client._listscripts(conn)
        finally:
            try:
                conn.logout()
            except Exception:
                pass
        self.write({'body': body,
                    'is_active_on_server': active_name == self.name})
        return True
