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
from openerp.exceptions import Warning, ValidationError
import re
import logging
_logger = logging.getLogger(__name__)

class res_users(models.Model):
    _inherit = 'res.users' 
       
    @api.one
    def write(self,values):
        result = super(res_users, self).write(values)
        if values.get('login') and self.alias_id:
            email_re = re.compile(r"""^([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,6})$""", re.VERBOSE)
            if not email_re.match(values.get('login')):  # login is not an email address
                self.alias_id.alias_name = values.get('login')
            else:
                self.alias_id.alias_name = email_re.match(values.get('login')).groups()[0] or ''
            #raise Warning('%s match %s' % (values.get('login'),email_re.match(values.get('login')) and email_re.match(values.get('login')).groups()) or '')
