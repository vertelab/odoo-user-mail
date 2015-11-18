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

    @api.one
    def _passwd_tmp(self):
        user_pw = self.env['res.users.password'].search([('user_id','=',self.id)])
        self.passwd_tmp = user_pw.passwd_tmp and user_pw.passwd_tmp or _('N/A') 
               
    passwd_tmp = fields.Char(compute='_passwd_tmp',string='Password')    


    @api.one
    def write(self,values):
        passwd = values.get('password') or values.get('new_password')
        if passwd:            
            self.env['res.users.password'].update_pw(self.id, passwd)
        return super(res_users, self).write(values)

    @api.model
    def create(self, values):
        passwd = values.get('password') or values.get('new_password')
        if passwd:
            self.env['res.users.password'].update_pw(self.id, passwd)
        return super(res_users, self).create(values)

class users_password(models.TransientModel):
    _name = "res.users.password"

    user_id = fields.Many2one(comodel_name='res.users',string="User")
    passwd_tmp = fields.Char('Password')

    @api.model
    def update_pw(self, user_id, pw):
        pw_user = self.search([('user_id','=',user_id)])
        if pw_user:            
            pw_user.passwd_tmp = pw
        else:
            self.create({'user_id': user_id, 'passwd_tmp': pw})
        return pw
