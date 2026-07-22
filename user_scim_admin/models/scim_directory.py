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
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ScimDirectoryUser(models.Model):
    """En LDAP-användare sedd genom SCIM-bridgen.

    Synkas från SCIM-bridgens /scim/v2/Users (med admin API-nyckel).
    Visar alla användare från alla kunder i en gemensam vy.
    """
    _name = 'scim.directory.user'
    _description = 'SCIM Directory User'
    _rec_name = 'display_name'
    _order = 'customer, display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ---------------------------------------------------------------------------
    # SCIM-FÄLT (core 2.0 User)
    # ---------------------------------------------------------------------------
    scim_id = fields.Char('SCIM ID', readonly=True, index=True,
        help='Unikt ID i SCIM-bridgen (uid)')
    display_name = fields.Char('Display Name', readonly=True, index=True)
    user_name = fields.Char('Username', readonly=True)
    given_name = fields.Char('Given Name', readonly=True)
    family_name = fields.Char('Family Name', readonly=True)
    email_primary = fields.Char('Primary Email', readonly=True)
    email_other = fields.Char('Other Email', readonly=True)
    active_scim = fields.Boolean('Active in LDAP', readonly=True)

    # ---------------------------------------------------------------------------
    # VERTEL-ATTRIBUT (extension)
    # ---------------------------------------------------------------------------
    customer = fields.Char('Customer', readonly=True, index=True,
        help='Kundens OU-namn i LDAP')
    quota = fields.Integer('Quota (MB)', readonly=True)
    forward_address = fields.Char('Forward Address', readonly=True)
    forward_active = fields.Boolean('Forward Active', readonly=True)
    spam_kill_level = fields.Char('Spam Kill Level', readonly=True)
    phone_number = fields.Char('Phone', readonly=True)
    mobile = fields.Char('Mobile', readonly=True)

    # Matrix (fylls i om user_scim_matrix är aktiv)
    matrix_id = fields.Char('Matrix ID', readonly=True)

    # ---------------------------------------------------------------------------
    # SYNK-METADATA
    # ---------------------------------------------------------------------------
    last_sync = fields.Datetime('Last Synced', readonly=True, default=fields.Datetime.now)
    last_seen = fields.Datetime('Last Seen in LDAP', readonly=True)

    # ---------------------------------------------------------------------------
    # COMPUTED
    # ---------------------------------------------------------------------------
    has_matrix = fields.Boolean('Has Matrix ID', compute='_compute_flags', search='_search_has_matrix')
    has_forward = fields.Boolean('Has Forward', compute='_compute_flags')
    is_active_user = fields.Boolean('Is Active', compute='_compute_flags')

    def _compute_flags(self):
        for r in self:
            r.has_matrix = bool(r.matrix_id)
            r.has_forward = r.forward_active
            r.is_active_user = r.active_scim

    def _search_has_matrix(self, operator, value):
        if operator == '=' and value:
            return [('matrix_id', '!=', False)]
        return [('matrix_id', '=', False)]

    # ---------------------------------------------------------------------------
    # SYNK ALLA ANVÄNDARE FRÅN SCIM-BRIDGE
    # ---------------------------------------------------------------------------
    @api.model
    def sync_all(self):
        """Hämta alla användare från SCIM-bridgen och uppdatera lokala poster."""
        IParam = self.env['ir.config_parameter'].sudo()
        bridge_url = IParam.get_param('scim.bridge_url', '').rstrip('/')
        api_key = IParam.get_param('scim.admin_api_key', '')
        verify = IParam.get_param('scim.verify_ssl', 'True') == 'True'

        if not bridge_url or not api_key:
            _logger.warning("SCIM bridge not configured for directory sync")
            return 0

        headers = {
            "X-SCIM-API-Key": api_key,
            "Accept": "application/scim+json",
        }

        try:
            r = requests.get(
                f"{bridge_url}/scim/v2/Users?count=500",
                headers=headers,
                verify=verify,
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            _logger.error(f"SCIM directory sync failed: {e}")
            return 0

        resources = data.get('Resources', [])
        now = fields.Datetime.now()
        synced_ids = []
        # Lagra synkfel per uid för detaljerad loggning
        errors = []

        for user in resources:
            scim_id = user.get('id')
            if not scim_id:
                continue

            ext = user.get(
                "urn:vertel:params:scim:schemas:extension:vertel:2.0:User",
                {}
            )
            emails = user.get('emails', [])
            email_primary = ''
            email_other = ''
            for e in emails:
                if e.get('primary'):
                    email_primary = e.get('value', '')
                else:
                    email_other = e.get('value', '')

            vals = {
                'scim_id': scim_id,
                'display_name': user.get('name', {}).get('formatted', '') or user.get('userName', ''),
                'user_name': user.get('userName', ''),
                'given_name': user.get('name', {}).get('givenName', ''),
                'family_name': user.get('name', {}).get('familyName', ''),
                'email_primary': email_primary,
                'email_other': email_other,
                'active_scim': user.get('active', True),
                'customer': ext.get('customer', ''),
                'quota': ext.get('quota', 0),
                'forward_address': ext.get('forwardAddress', ''),
                'forward_active': ext.get('forwardActive', False),
                'spam_kill_level': ext.get('spamKillLevel', '6'),
                'phone_number': ext.get('phoneNumber', ''),
                'mobile': ext.get('mobile', ''),
                'matrix_id': ext.get('matrixId', ''),
                'last_sync': now,
                'last_seen': now,
            }

            existing = self.search([('scim_id', '=', scim_id)], limit=1)
            try:
                if existing:
                    existing.write(vals)
                    synced_ids.append(existing.id)
                else:
                    record = self.create(vals)
                    synced_ids.append(record.id)
            except Exception as e:
                errors.append(f"{scim_id}: {e}")
                _logger.error(f"SCIM directory sync error for {scim_id}: {e}")

        # Markera användare som inte längre finns i SCIM
        if synced_ids:
            missing = self.search([('id', 'not in', synced_ids)])
            if missing:
                _logger.info(
                    f"SCIM directory: {len(missing)} users no longer in LDAP"
                )
                missing.unlink()

        if errors:
            _logger.warning(f"SCIM directory sync completed with {len(errors)} errors")

        return len(synced_ids)

    # ---------------------------------------------------------------------------
    # ACTION: MANUELL SYNK
    # ---------------------------------------------------------------------------
    def action_sync_from_bridge(self):
        """Manuell synk från SCIM-bridge."""
        count = self.sync_all()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('SCIM Directory Sync'),
                'message': _('%(count)s users synced from LDAP') % {'count': count},
                'sticky': False,
                'type': 'success',
            }
        }

    # ---------------------------------------------------------------------------
    # ACTION: ÖPPNA I KUNDENS ODOO (framtida)
    # ---------------------------------------------------------------------------
    def action_open_customer_odoo(self):
        """Öppna användaren i kundens Odoo (om länk finns)."""
        # TODO: Implementera när vi har per-kund Odoo-URL i systemparametrar
        raise UserError(_("Customer Odoo link not yet configured."))


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    scim_admin_api_key = fields.Char(
        string='SCIM Admin API Key',
        help='API-nyckel med admin-behörighet på SCIM-bridgen.\n'
             'Krävs för att ledningssystemet ska kunna läsa alla användare.',
        config_parameter='scim.admin_api_key',
    )
