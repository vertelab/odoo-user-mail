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

class res_users(models.Model):
    _inherit = 'res.users' 

    @api.model
    def create(self, values):
		#_logger.info("In create serverside::::::::::::::")
		ctx = self.env.context.copy()
		ctx.update({'no_reset_password' : True})
		return super(res_users, self.with_context(ctx)).create(values)

    @api.one
    def write(self,values):
        #raise Warning(values)
        if values.get('password') and not values.get('dovecot_password',False):
            _logger.info('creates dovecot_password from %s' % values)
            from passlib.hash import sha512_crypt
            values['dovecot_password'] = sha512_crypt.encrypt(values.get('password'))
        return super(res_users, self).write(values)

    #~ @api.one
    #~ def unlink(self):
        user_id = self.env['res.users'].search([('login','=',self.login)]).id
        postfix_alias_id = self.env['postfix.alias'].search([('user_id', '=', self.id)]).unlink()
        #~ self.postfix_alias_ids.unlink()
        #~ return super(res_users, self).unlink()

