# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015- Vertel AB (<http://www.vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
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
import logging

from odoo import models, fields, api, _
from odoo.exceptions import Warning
from passlib.hash import sha512_crypt

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users' 

    @api.model
    def create(self, values):
        ctx = self.env.context.copy()
        ctx.update({'no_reset_password': True})
        return super(ResUsers, self.with_context(ctx)).create(values)

    @api.multi
    def write(self, values):
        if values.get('password') and not values.get('dovecot_password', False):
            _logger.info('creates dovecot_password from %s' % values)
            values['dovecot_password'] = sha512_crypt.encrypt(values.get('password'))
        return super(ResUsers, self).write(values)

    def unlink(self):
        self.env['postfix.alias'].search([('user_id', '=', self.id)]).unlink()
        return super(ResUsers, self).unlink()

