# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2020- Vertel AB (<http://www.vertel.se>).
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
from openerp import models, fields, api, _

import logging
_logger = logging.getLogger(__name__)


class MailMessage(models.Model):
    _inherit = 'mail.message'
    
    @api.model
    def message_mark_all_as_read(self):
        """ Set as read. """
        partner_id = self.env.user.partner_id.id
        self.env.cr.execute('''
            UPDATE mail_notification SET
                is_read=true
            WHERE
                partner_id = %s
        ''', (partner_id,))
        self.env['mail.notification'].invalidate_cache(['is_read'])
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',  
        }
    

    
