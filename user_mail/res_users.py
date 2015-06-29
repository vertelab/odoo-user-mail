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


from openerp import models, fields, api, _
import openerp.tools

import logging
_logger = logging.getLogger(__name__)


class res_users(models.Model):
    _inherit = 'res.users'

    passwd_server = openerp.tools.config.get('passwd_server',False)
    _logger.warning('Passwd_server %s' % passwd_server)

    @api.one
    def _maildir_get(self):
        self.maildir = "%s/%s/" % (self.company_id.domain,self.user_email)


    postfix_active = fields.Boolean('Active',default=True)
    #      'full_email': fields.function(_full_email,string='Full Email',type="char",size=64,store=True,select=1),
    vacation_subject = fields.Char('Subject', size=64,)
    vacation_text =  fields.Text('Text')
    vacation_active =  fields.Boolean('Active',default=False)
    vacation_from = fields.Date('From')
    vacation_to = fields.Date('To')
    vacation_forward = fields.Char('Forward', size=64,)
    forward_active = fields.Boolean('Active',default=False)
    forward_address = fields.Text('Forward address',help='Comma separated list of mail addresses' )
    forward_cp = fields.Boolean('Keep')
    virus_active = fields.Boolean('Virus Check',default=True)
    spam_active = fields.Boolean('Spam Check',default=True)
    spam_killevel = fields.Selection([(10.0,'low (10)'),(6.0,'medium (6)'),(4.5,'high (4.5)'),(3.0,'very high (3)')],'Spam Kill Level', help="Killed spam never reach your mail client",default=6.0)
    spam_tag2 = fields.Selection([(9.5,'low (9.5)'),(5.5,'medium (5.5)'),(4.0,'high (4)'),(2.5,'very high (2.5)')],'Spam Tag Level', help="Tagged spam will be marked as spam in your mail client and usually sorted in the spam directory",default=5.5)
    spam_tag = fields.Selection([(7.0,'low (7)'),(3.0,'medium (3)'),(1.5,'high (1.5)'),(0.0,'very high (0)')],'Spam Tag Level', help="Tagged spam will be marked as spam in your mail client",default=3.0)
    maildir = fields.Char(compute="_maildir_get",string='Maildir',size=64,store=True,select=1)
    transport = fields.Char('Transport', size=64,default="virtual:")
    @api.one
    def _quota_get(self):
        return self.company_id.default_quota
    quota = fields.Integer('Quota',default=_quota_get)
    domain  = fields.Char(related="company_id.domain",string='Domain', size=64,store=True, readonly=True)
    #        'mail': fields.char('Mail', size=64,),
    #        'mail_active': fields.boolean('Active'),
    alias_mail = fields.One2many('postfix.alias', 'user_id', 'Alias_mail',)
    
    @api.v8
    def change_password(self,old_passwd, new_passwd, context=None):
        """Change current user password. Old password must be provided explicitly
        to prevent hijacking an existing user session, or for cases where the cleartext
        password is not used to authenticate requests.

        :return: True
        :raise: openerp.exceptions.AccessDenied when old password is wrong
        :raise: except_osv when new password is not set or empty
        """
        if super(res_users, self).change_password(old_passwd, new_passwd, context=context):
            pass # Update database
            
#        raise osv.except_osv(_('Warning!'), _("Setting empty passwords is not allowed for security reasons!"))


    
class res_company(models.Model):
    _inherit = 'res.company'
    
    domain = fields.Char('Domain',help="the internet domain for mail")
    
    @api.one
    def _total_quota(self):
        self.total_quota = sum([u.quota for u in self.env['res.users'].search([('company_id','=',self.id)])])

    default_quota = fields.Integer('Quota',)
    total_quota  = fields.Integer(compute="_total_quota",string='Quota total',)

class postfix_vacation_notification(models.Model):
    _name = 'postfix.vacation_notification'
    user_id = fields.Many2one('res.users','User', required=True,)
    notified = fields.Char('Notified',size=64,select=1)
    date = fields.Date('Date',default=fields.Date.context_today)
    
class postfix_alias(models.Model):
    _name = 'postfix.alias'
    user_id = fields.Many2one('res.users','User', required=True,)
    mail    = fields.Char('Mail', size=64, help="Mail as <user>@<domain>, if you are using a foreign domain, make sure that this domain are handled by the same mailserver"),
 #       'goto': fields.related('user_id', 'maildir', type='many2one', relation='res.users', string='Goto', store=True, readonly=True),
    active = fields.Boolean('Active',default=True)
