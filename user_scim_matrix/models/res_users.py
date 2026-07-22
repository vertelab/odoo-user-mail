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

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ---------------------------------------------------------------------------
    # MATRIX-FÄLT (kräver user_matrix)
    # ---------------------------------------------------------------------------
    matrix_id = fields.Char('Matrix ID',
        help='Matrix-användare, t.ex. @waland:matrix.vertel.se\n'
             'Detta synkas till LDAP och kan användas av Element/element-web.')

    # ---------------------------------------------------------------------------
    # UTÖKA SCIM-STYRANDE FÄLT
    # ---------------------------------------------------------------------------
    def _get_scim_fields(self):
        """Lägg till matrix_id i listan över fält som triggar SCIM-push."""
        fields = super()._get_scim_fields()
        fields.append('matrix_id')
        return fields

    # ---------------------------------------------------------------------------
    # HOOK: UTÖKA SCIM-JSON
    # ---------------------------------------------------------------------------
    def _scim_extend_json(self, scim_data):
        """Lägg till matrixId i vertel-extension-blocket."""
        scim_data = super()._scim_extend_json(scim_data)
        if self.matrix_id:
            scim_data.setdefault(
                "urn:vertel:params:scim:schemas:extension:vertel:2.0:User", {}
            )["matrixId"] = self.matrix_id
        return scim_data
