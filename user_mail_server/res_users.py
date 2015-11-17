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


class postfix_vacation_notification(models.Model):
    _inherit = 'postfix.vacation_notification'
    
class postfix_alias(models.Model):
    _inherit = 'postfix.alias'


class res_users(models.Model):
    _inherit = 'res.users' 
    
    def _get_param(self,param,value):
        if not self.env['ir.config_parameter'].get_param(param):
            self.env['ir.config_parameter'].set_param(param,value)
        return self.env['ir.config_parameter'].get_param(param)

    @api.model
    def create(self, values):      
        user = super(res_users, self).create(values)
        if values.get('name') == 'Catchall':
            self.env['res.users.password'].update_pw(user.id, values.get('new_password'))

        return user

    @api.one
    def unlink(self):
        user_id = self.env['res.users'].search([('login','=',self.login)]).id
        postfix_alias_id = self.env['postfix.alias'].search([('user_id', '=', user_id)]).unlink()

        return super(res_users, self).unlink()
            
class res_company(models.Model):
    _inherit = 'res.company'
  
    def _get_param(self,param,value):
        if not self.env['ir.config_parameter'].get_param(param):
            self.env['ir.config_parameter'].set_param(param,value)
        return self.env['ir.config_parameter'].get_param(param)

