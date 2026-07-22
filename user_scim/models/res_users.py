# -*- coding: utf-8 -*-
##############################################################################
#
#    Vertel AB (<http://www.vertel.se>)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
##############################################################################

import logging
import requests

from odoo import models, fields, api, _
from odoo.tools import config as odoo_config

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ---------------------------------------------------------------------------
    # SCIM-FÄLT (infrastrukturella)
    # ---------------------------------------------------------------------------
    scim_id = fields.Char('SCIM ID', copy=False, index=True,
        help='ID från SCIM-servern (LDAP). Sätts automatiskt vid första synk.')
    scim_last_sync = fields.Datetime('Last SCIM Sync', readonly=True,
        help='Senaste gången användaren synkades till SCIM-bridge.')
    scim_sync_error = fields.Text('SCIM Sync Error', readonly=True,
        help='Senaste synk-felet, om något.')

    # ---------------------------------------------------------------------------
    # VERTEL-SPECIFIKA FÄLT (utöver user_mail_common)
    # ---------------------------------------------------------------------------
    forward_active = fields.Boolean('Forward Active', default=False,
        help='Vidarebefordra e-post till extern adress.')
    forward_address = fields.Char('Forward Address',
        help='E-postadress att vidarebefordra till.')
    spam_kill_level = fields.Selection([
        ('10', 'Low (10)'),
        ('6', 'Medium (6)'),
        ('4.5', 'High (4.5)'),
        ('3', 'Very High (3)'),
    ], string='Spam Kill Level', default='6',
        help='Nivå för att döda spam.')
    quota = fields.Integer('Quota (MB)', default=200,
        help='Mailbox quota i MB.')

    # ---------------------------------------------------------------------------
    # SCIM-FÄLT SOM SYNKAS (bas)
    # ---------------------------------------------------------------------------
    def _get_scim_fields(self):
        """Returnera lista med fält som triggar SCIM-push.

        Kan överskrivas av extensions (user_scim_matrix m.fl.)
        för att lägga till fler fält.
        """
        return [
            'name', 'login', 'email',
            'postfix_active', 'postfix_mail',
            'forward_active', 'forward_address',
            'quota', 'spam_kill_level',
        ]

    def _get_scim_config(self):
        """Hämta SCIM-konfiguration.

        Prioriteringsordning:
        1. tools.config (odoo.conf — sätts via Salt pillar)
        2. ir.config_parameter (per-database — används på multi-DB-servrar)
        3. Tomt — bridge och nyckel måste konfigureras
        """
        IParam = self.env['ir.config_parameter'].sudo()

        bridge_url = odoo_config.get('scim_bridge_url', '') or IParam.get_param('scim.bridge_url', '')
        api_key = odoo_config.get('scim_api_key', '') or IParam.get_param('scim.api_key', '')
        verify = odoo_config.get('scim_verify_ssl', '') or IParam.get_param('scim.verify_ssl', 'True')

        return {
            'bridge_url': bridge_url.rstrip('/'),
            'api_key': api_key,
            'verify_ssl': str(verify).lower() == 'true',
        }

    # ---------------------------------------------------------------------------
    # HOOK: utökad SCIM-JSON
    # ---------------------------------------------------------------------------
    def _scim_extend_json(self, scim_data):
        """Hook för utökade moduler (user_scim_matrix m.fl.)

        Anropas från _scim_to_json() efter att bas-JSON:en byggts.
        Överskriv i ärvande moduler för att lägga till fält i
        vertel-extension-blocket.

        Exempel:
            def _scim_extend_json(self, scim_data):
                scim_data["urn:vertel:params:scim:schemas:extension:vertel:2.0:User"]["matrixId"] = self.matrix_id
                return scim_data
        """
        return scim_data

    # ---------------------------------------------------------------------------
    # BYGG SCIM-JSON
    # ---------------------------------------------------------------------------
    def _scim_to_json(self):
        """Konvertera Odoo-användare till SCIM 2.0 JSON.

        Returnerar ett SCIM User-objekt enligt:
        https://tools.ietf.org/html/rfc7643#section-4.1
        """
        self.ensure_one()

        company = self.company_id

        scim = {
            "schemas": [
                "urn:ietf:params:scim:schemas:core:2.0:User",
                "urn:vertel:params:scim:schemas:extension:vertel:2.0:User",
            ],
            "userName": self.postfix_mail or self.login or self.email or self.name,
            "name": {
                "formatted": self.name or '',
                "givenName": (self.name or '').split(' ')[0] if self.name else '',
                "familyName": ' '.join((self.name or '').split(' ')[1:]) if self.name and ' ' in self.name else (self.name or ''),
            },
            "emails": [],
            "active": self.active and self.postfix_active,
            "urn:vertel:params:scim:schemas:extension:vertel:2.0:User": {
                "customer": company.name if company else '',
                "quota": self.quota or 0,
                "forwardAddress": self.forward_address or '',
                "forwardActive": bool(self.forward_active),
                "spamKillLevel": self.spam_kill_level or '6',
                "phoneNumber": self.phone or '',
                "mobile": self.mobile or '',
            },
        }

        # E-post
        if self.postfix_mail:
            scim["emails"].append({
                "value": self.postfix_mail,
                "type": "work",
                "primary": True,
            })
        if self.email and self.email != self.postfix_mail:
            scim["emails"].append({
                "value": self.email,
                "type": "other",
                "primary": False,
            })

        # Alias från user_mail_common
        if hasattr(self, 'postfix_alias_ids') and self.postfix_alias_ids:
            aliases = [a.mail for a in self.postfix_alias_ids if a.active]
            if aliases:
                scim["urn:vertel:params:scim:schemas:extension:vertel:2.0:User"]["emailAliases"] = aliases

        # HOOK: låt utökade moduler lägga till sina fält
        scim = self._scim_extend_json(scim)

        return scim

    # ---------------------------------------------------------------------------
    # PUSHA TILL SCIM-BRIDGE
    # ---------------------------------------------------------------------------
    def _scim_push(self):
        """Push changes to SCIM bridge.

        Anropar SCIM 2.0 API:
        - POST /scim/v2/Users — om användaren inte finns i LDAP än
        - PUT /scim/v2/Users/{uid} — om användaren redan finns
        - DELETE /scim/v2/Users/{uid} — om användaren inaktiveras
        """
        config = self._get_scim_config()
        if not config['bridge_url']:
            _logger.warning("SCIM bridge not configured — set 'scim.bridge_url'")
            return
        if not config['api_key']:
            _logger.warning("SCIM API key not configured — set 'scim.api_key'")
            return

        headers = {
            "X-SCIM-API-Key": config['api_key'],
            "Content-Type": "application/scim+json",
            "Accept": "application/scim+json",
        }
        verify = config['verify_ssl']

        for record in self:
            uid = record.login.split('@')[0] if record.login else record.name
            try:
                # Inaktiverad eller postfix_inactive → ta bort från LDAP
                if not record.active or not record.postfix_active:
                    if record.scim_id:
                        r = requests.delete(
                            f"{config['bridge_url']}/scim/v2/Users/{uid}",
                            headers=headers,
                            verify=verify,
                            timeout=10,
                        )
                        if r.status_code in (200, 204, 404):
                            record.write({'scim_id': False, 'scim_last_sync': fields.Datetime.now()})
                            _logger.info(f"SCIM deleted {uid}")
                    continue

                # Skapa eller uppdatera
                scim_data = record._scim_to_json()

                if record.scim_id:
                    r = requests.put(
                        f"{config['bridge_url']}/scim/v2/Users/{uid}",
                        json=scim_data,
                        headers=headers,
                        verify=verify,
                        timeout=10,
                    )
                else:
                    r = requests.post(
                        f"{config['bridge_url']}/scim/v2/Users",
                        json=scim_data,
                        headers=headers,
                        verify=verify,
                        timeout=10,
                    )

                if r.status_code in (200, 201):
                    record.write({
                        'scim_id': uid,
                        'scim_last_sync': fields.Datetime.now(),
                        'scim_sync_error': False,
                    })
                    _logger.info(f"SCIM synced {uid} ({r.status_code})")
                elif r.status_code == 409:
                    error_detail = r.json().get('detail', 'Conflict')
                    record.write({'scim_sync_error': error_detail})
                    _logger.warning(f"SCIM conflict {uid}: {error_detail}")
                else:
                    error_msg = f"HTTP {r.status_code}: {r.text[:200]}"
                    record.write({'scim_sync_error': error_msg})
                    _logger.error(f"SCIM error {uid}: {error_msg}")

            except requests.exceptions.ConnectionError as e:
                error_msg = f"Connection error: {e}"
                record.write({'scim_sync_error': error_msg})
                _logger.error(f"SCIM connection error {uid}: {e}")
            except Exception as e:
                error_msg = f"Error: {e}"
                record.write({'scim_sync_error': error_msg})
                _logger.error(f"SCIM error {uid}: {e}")

    # ---------------------------------------------------------------------------
    # OVERRIDES — kör SCIM-push vid ändringar
    # ---------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        for user in users:
            if user.postfix_active:
                try:
                    user._scim_push()
                except Exception:
                    _logger.exception("SCIM push failed on create")
        return users

    def write(self, vals):
        result = super().write(vals)

        scim_fields = [f for f in self._get_scim_fields() if f in vals]
        if scim_fields:
            for record in self:
                try:
                    record._scim_push()
                except Exception:
                    _logger.exception(f"SCIM push failed on write for {record.login}")

        return result

    def unlink(self):
        for record in self:
            if record.postfix_active or record.scim_id:
                try:
                    record.write({'postfix_active': False})
                    record._scim_push()
                except Exception:
                    _logger.exception(f"SCIM push failed on unlink for {record.login}")
        return super().unlink()

    # ---------------------------------------------------------------------------
    # ACTION: MANUELL SCIM-SYNK
    # ---------------------------------------------------------------------------

    def action_scim_sync(self):
        """Manuell synk — anrops från användarformuläret."""
        for record in self:
            record._scim_push()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('SCIM Sync'),
                'message': _('Users synced to SCIM bridge.'),
                'sticky': False,
                'type': 'success',
            }
        }


class ResCompany(models.Model):
    _inherit = 'res.company'

    def write(self, vals):
        result = super().write(vals)
        if 'domain' in vals:
            users = self.env['res.users'].sudo().search([
                ('company_id', 'in', self.ids),
                ('postfix_active', '=', True),
            ])
            if users:
                _logger.info(f"Domain changed — resyncing {len(users)} users via SCIM")
                users._scim_push()
        return result
