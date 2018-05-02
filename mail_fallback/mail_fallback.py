# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2018- Vertel AB (<http://www.vertel.se>).
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
import openerp.tools
import re

import logging
_logger = logging.getLogger(__name__)


class mail_fallback(models.Model):
    _name = 'mail.fallback'
    _description = "Fallback Mail"
    _inherit = ['mail.thread']
    

    
    name = fields.Char()
    body = fields.Text()
    message_id = fields.Char()
    author_id = fields.Many2one(comodel_name="res.partner")
    mail_message = fields.Many2one(comodel_name="mail.messsage")
    #~ attachment_ids = fields.Many2many(comodel_name="ir.attachment")
    #~ from = fields.Char()
    cc = fields.Char()
    to = fields.Char()
    type = fields.Char()
    email_from = fields.Char()
    email_to = fields.Char()
    state = fields.Selection(selection=[('draft','Draft'),('active','Active'),('canceled','Canceled')])

 #~ dict {'body': u'\n<pre>llll\r\n\r\n\r\n\r\n\r\n\xf6k\xf6\xe4k\r\n\r\n\r\n\r\n\r\n\r\n</pre>\n', 
 #~ 'from': u'Anders Wallenquist <anders@wallenquist.se>', 
 #~ 'attachments': [], 
 #~ 'cc': None, 
 #~ 'email_from': u'Anders Wallenquist <anders@wallenquist.se>',
  #~ 'to': u'sture@azzar.se', 'date': '2018-04-24 14:41:36', 
  #~ 'partner_ids': [], 'type': 'email', 
  #~ 'message_id': '<ec091126-f856-d328-0d6f-011bcb2e1104@wallenquist.se>', 
  #~ 'subject': u'test 9'} model mail.fallback thread_id None custom None context {'lang': 'sv_SE', 'tz': False, 'uid': 1, 
  #~ 'fetchmail_cron_running': True, 'server_type': u'imap', 'fetchmail_server_id': 1, 'params': {'action': 106}}



    @api.model
    def create(self,values):
        _logger.warn('values %s' % values)
        fallback = super(mail_fallback,self).create(values)
        _logger.warn('fallback %s' % fallback)
        mail = self.env['mail.message'].search([('model','=','mail.fallback'),('res_id','=',fallback.id)],limit=1)
        if mail:
            fallback.mail_message = mail.id
            
        return fallback


class mail_thread(models.TransientModel):
    _inherit = 'mail.thread'

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        _logger.warn('message_new values %s custom %s context %s ' % (msg_dict,custom_values,self.env.context))
        return super(mail_thread,self).message_new(msg_dict,custom_values)
    
    @api.model
    def message_route(self,message, message_dict, model=None, thread_id=None,custom_values=None):
        _logger.warn(u'message_route message  dict %s model %s thread_id %s custom %s context %s ' % ( message_dict, model, thread_id,custom_values,self.env.context))
        #~ _logger.warn(u'message_route message  dict %s model %s thread_id %s custom %s context %s ' % (message, message_dict, model, thread_id,custom_values,self.env.context))
        return super(mail_thread,self).message_route(message, message_dict, model, thread_id,custom_values)

    @api.model
    def message_route_verify(self, message, message_dict, route, update_author=True, assert_model=True, create_fallback=True, allow_private=False):
        """ Verify route validity. Check and rules:
        """
        _logger.warn(u'message_route_verify   dict %s route %s thread_id %s custom %s context %s %s ' % ( message_dict, route, update_author,assert_model,create_fallback,allow_private))
        return super(mail_thread,self).message_route_verify(message, message_dict, route, update_author, assert_model, create_fallback, allow_private)

    @api.cr_uid_ids_context
    def message_post(self, cr, uid, thread_id, body='', subject=None, type='notification',
                     subtype=None, parent_id=False, attachments=None, context=None,
                     content_subtype='html', **kwargs):
        """ Post a new message in an existing thread, to a non existing recipient. For example a new project.issue
"""
        # Chech if email_from on project.issue are in res.partner
        mail_message = self.pool.get('mail.message').browse(cr,uid,parent_id,context)
        if mail_message:
            mail_object = self.pool.get(mail_message.model).browse(cr,uid,mail_message.res_id,context)
            if mail_object:
                if 'email_from' in mail_object.fields_get_keys() and mail_object.email_from:
                    if not ('partner_id' in mail_object.fields_get_keys() and mail_object.partner_id):
                        m = re.search("(.*)<(.*@.*)>",mail_object.email_from)
                        if '@' in m.group(1):
                            email = m.group(1)
                            name = m.group(1)
                        else:
                            name = m.group(1)
                            email = m.group(2)
                        if email and len(self.pool.get('res.partner').search(cr,uid,[('email','=',email)])) == 0: # Create partner and add as follower
                            partner_id = self.pool.get('res.partner').create(cr,uid,{'name': name,'email': email})
                            mail_object.write({
                                'partner_id': partner_id,
                                'message_follower_ids': [(4,partner_id,0)],
                            })
                
        _logger.warn(u'message_POST   dict %s route %s thread_id %s custom %s context %s %s ' % (thread_id, body, subject, type,subtype, parent_id))
        return super(mail_thread,self).message_post(cr,uid,thread_id, body, subject, type,subtype, parent_id, attachments, context,content_subtype, **kwargs)
