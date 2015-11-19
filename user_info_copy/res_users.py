# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015- Vertel AB (<http://www.vertel.se>).
#
#    This progrupdateam is free software: you can redistribute it and/or modify
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
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import models, fields, api, _
from openerp.exceptions import Warning
import logging
_logger = logging.getLogger(__name__)

class user_information(models.Model):
    _inherit = "res.users"

    dovecot_password_copy = fields.Char('Dovecot Password Copy')

    def _copy_dovecot_passwords(self, cr, uid, ids, context=None):
        users = self.browse(cr, uid, ids, context)
        for user in users:
            user.write({'dovecot_password_copy': user.dovecot_password})

    def _set_dovecot_passwords(self, cr, uid, ids, context=None):
        users = self.browse(cr, uid, ids, context)
        for user in users:
            user.write({'dovecot_password': user.dovecot_password_copy})

    @api.model
    def add_to_more_button(self):
        record = self.env.ref("user_info_copy.copy_action")
        record.create_action()


class module(models.Model):
    _inherit = "ir.module.module"   

    def module_uninstall(self, cr, uid, ids, context=None):
        user_ids = self.pool.get('res.users').search(cr, uid, [], context)
        self.pool.get('res.users')._copy_dovecot_passwords(cr, uid, user_ids, context)

        return super(module, self).module_uninstall(cr, uid, ids, context)