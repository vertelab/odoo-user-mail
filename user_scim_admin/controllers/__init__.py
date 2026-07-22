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

from odoo import http
from odoo.http import request
from odoo.tools import config as odoo_config

_logger = logging.getLogger(__name__)


def _scim_config(key, default=''):
    """Läs SCIM-konfig: tools.config → ir.config_parameter → default."""
    from odoo import http
    val = odoo_config.get(key, '')
    if not val:
        IParam = http.request.env['ir.config_parameter'].sudo()
        val = IParam.get_param(key, default)
    return val


class ScimDirectoryController(http.Controller):

    def _scim_admin_config(self):
        """Hämta admin-config från tools.config eller ir.config_parameter."""
        IParam = request.env['ir.config_parameter'].sudo()
        bridge_url = odoo_config.get('scim_bridge_url', '') or IParam.get_param('scim.bridge_url', '')
        api_key = odoo_config.get('scim_admin_api_key', '') or IParam.get_param('scim.admin_api_key', '')
        verify = odoo_config.get('scim_verify_ssl', '') or IParam.get_param('scim.verify_ssl', 'True')
        return {
            'bridge_url': bridge_url.rstrip('/'),
            'api_key': api_key,
            'verify_ssl': str(verify).lower() == 'true',
        }

    @http.route('/scim/dashboard/overview', type='json', auth='user')
    def scim_dashboard_overview(self):
        """Dashboard — statistik över alla kunders användare."""
        if not request.env.user.has_group('base.group_system'):
            return {'error': 'Access denied'}

        cfg = self._scim_admin_config()
        if not cfg['bridge_url'] or not cfg['api_key']:
            return {'error': 'SCIM bridge not configured'}

        try:
            r = requests.get(
                f"{cfg['bridge_url']}/admin/overview",
                headers={"X-SCIM-API-Key": cfg['api_key']},
                verify=cfg['verify_ssl'],
                timeout=10,
            )
            return r.json()
        except Exception as e:
            return {'error': str(e)}

    @http.route('/scim/dashboard/conflicts', type='json', auth='user')
    def scim_dashboard_conflicts(self):
        """Dashboard — konflikter mellan kunder."""
        if not request.env.user.has_group('base.group_system'):
            return {'error': 'Access denied'}

        cfg = self._scim_admin_config()
        if not cfg['bridge_url'] or not cfg['api_key']:
            return {'error': 'SCIM bridge not configured'}

        try:
            r = requests.get(
                f"{cfg['bridge_url']}/admin/conflicts",
                headers={"X-SCIM-API-Key": cfg['api_key']},
                verify=cfg['verify_ssl'],
                timeout=10,
            )
            return r.json()
        except Exception as e:
            return {'error': str(e)}

    @http.route('/scim/webhook', type='json', auth='public', methods=['POST'], csrf=False)
    def scim_webhook(self):
        """Webhook från SCIM Bridge — LDAP-ändringar i realtid."""
        IParam = request.env['ir.config_parameter'].sudo()
        webhook_secret = odoo_config.get('scim_webhook_secret', '') or IParam.get_param('scim.webhook_secret', '')

        if webhook_secret:
            import hashlib, hmac, json
            sig_header = request.httprequest.headers.get('X-SCIM-Signature', '')
            if sig_header:
                payload = json.dumps(request.jsonrequest, sort_keys=True)
                expected = hmac.new(
                    webhook_secret.encode(), payload.encode(), hashlib.sha256
                ).hexdigest()
                if not hmac.compare_digest(expected, sig_header):
                    _logger.warning('Webhook: invalid signature')
                    return {'status': 'error', 'detail': 'Invalid signature'}

        payload = request.jsonrequest
        event = payload.get('event', '')
        uid = payload.get('uid', '')
        _logger.info(f'Webhook received: {event} for {uid}')

        DirectoryUser = request.env['scim.directory.user'].sudo()
        if event == 'scim.delete':
            existing = DirectoryUser.search([('scim_id', '=', uid)])
            if existing:
                existing.unlink()
                _logger.info(f'Webhook: removed {uid} from directory')
        else:
            IParam.set_param('scim.last_webhook', payload.get('timestamp', ''))

        return {'status': 'ok'}
