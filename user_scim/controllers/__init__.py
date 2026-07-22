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


class ScimAdminController(http.Controller):

    @http.route('/scim/dashboard/overview', type='json', auth='user')
    def scim_dashboard_overview(self):
        """Hämta SCIM-översikt för ledningssystemet.

        Anropar SCIM-bridgens admin-endpoint.
        Kräver att Odoo-användaren har 'scim.admin'-grupp (eller är admin).
        """
        if not request.env.user.has_group('base.group_system'):
            return {'error': 'Access denied — admin only'}

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
        """Hämta konflikter mellan kunder."""
        if not request.env.user.has_group('base.group_system'):
            return {'error': 'Access denied — admin only'}

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
