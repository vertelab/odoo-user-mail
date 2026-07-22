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

_logger = logging.getLogger(__name__)


class ScimDirectoryController(http.Controller):

    @http.route('/scim/dashboard/overview', type='json', auth='user')
    def scim_dashboard_overview(self):
        """Dashboard — statistik över alla kunders användare."""
        if not request.env.user.has_group('base.group_system'):
            return {'error': 'Access denied'}

        IParam = request.env['ir.config_parameter'].sudo()
        bridge_url = IParam.get_param('scim.bridge_url', '').rstrip('/')
        api_key = IParam.get_param('scim.admin_api_key', '')
        verify = IParam.get_param('scim.verify_ssl', 'True') == 'True'

        if not bridge_url or not api_key:
            return {'error': 'SCIM bridge not configured'}

        try:
            r = requests.get(
                f"{bridge_url}/admin/overview",
                headers={"X-SCIM-API-Key": api_key},
                verify=verify,
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

        IParam = request.env['ir.config_parameter'].sudo()
        bridge_url = IParam.get_param('scim.bridge_url', '').rstrip('/')
        api_key = IParam.get_param('scim.admin_api_key', '')
        verify = IParam.get_param('scim.verify_ssl', 'True') == 'True'

        if not bridge_url or not api_key:
            return {'error': 'SCIM bridge not configured'}

        try:
            r = requests.get(
                f"{bridge_url}/admin/conflicts",
                headers={"X-SCIM-API-Key": api_key},
                verify=verify,
                timeout=10,
            )
            return r.json()
        except Exception as e:
            return {'error': str(e)}

    @http.route('/scim/webhook', type='json', auth='public', methods=['POST'], csrf=False)
    def scim_webhook(self):
        """Webhook från SCIM Bridge — LDAP-ändringar i realtid."""
        IParam = request.env['ir.config_parameter'].sudo()
        webhook_secret = IParam.get_param('scim.webhook_secret', '')

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
