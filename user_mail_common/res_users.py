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
from openerp import tools
import re
import logging
_logger = logging.getLogger(__name__)

class postfix_vacation_notification(models.Model):
    _name = 'postfix.vacation_notification'
    #could not install because of the relation to user_id (postfix.alias has the same relation only one is allowed?)
    #user_id = fields.Many2one('res.users','User', required=True,)
    notified = fields.Char('Notified',size=64,select=1)
    date = fields.Date('Date',default=fields.Date.context_today)
    
class postfix_alias(models.Model):
    _name = 'postfix.alias'
    user_id = fields.Many2one('res.users', required=True)
    # concatenate with domain from res.company 
 #       'goto': fields.related('user_id', 'maildir', type='many2one', relation='res.users', string='Goto', store=True, readonly=True),
    active = fields.Boolean('Active',default=True)
    #~ @api.one
    #~ @api.depends('user_id.domain','mail_domain')
    #~ def _mail(self):
        #~ self.mail   = "%s@%s" % (self.mail_domain,self.user_id.domain)
    @api.one
    @api.onchange('user_id.company_id.domain','name')
    def _onchange_mail(self):
        self.mail = '%s@%s' % (self.name,self.user_id.company_id.domain)

    mail    = fields.Char(string='Complete Mail Address',size=64, help="Mail as <user>@<domain>, if you are using a foreign domain, make sure that this domain are handled by the same mailserver", store=True)
    name = fields.Char(string='Mailaddress',size=64, help="Mail without domain")

    # @api.one
    # @api.constrains('name')
    # def _check_mail(self):
    #     if len(self.user_id.company_id.user_ids.mapped('postfix_alias').filtered(lambda r: r.name == self.name))>1:
    #         raise ValidationError("E-mail address %s already taken (alias)" % self.mail)
    #     if len(self.user_id.company_id.user_ids.filtered(lambda r: r.email == self.mail))>1:
    #         raise ValidationError("E-mail address %s already taken (main)" % self.mail)

email_re = re.compile(r"""^([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,6})$""", re.VERBOSE)

class res_users(models.Model):
    _inherit = 'res.users' 

    postfix_active = fields.Boolean('Active', default=False,)
    vacation_subject = fields.Char('Subject', size=64,)
    vacation_text =  fields.Text('Text',help="Vacation message for autorespond")
    vacation_active =  fields.Boolean('Active',default=False)
    vacation_from = fields.Date('From',help="Vacation starts")
    vacation_to = fields.Date('To',help="Vacation ends")
    vacation_forward = fields.Char('Forward', size=64,help="Mailaddress to send messages during vacation")
    forward_active = fields.Boolean('Active',default=False)
    forward_address = fields.Text('Forward address',help='Comma separated list of mail addresses' )
    forward_cp = fields.Boolean('Keep',help="Keep a local copy of forwarded messages")
    virus_active = fields.Boolean('Virus Check',default=True)
    spam_active = fields.Boolean('Spam Check',default=True)
    spam_killevel = fields.Selection([('10','low (10)'),('6','medium (6)'),('4.5','high (4.5)'),('3','very high (3)')]  ,string='Spam Kill Level', help="Killed spam never reach your mail client",default='6')
    spam_tag2 =     fields.Selection([('9.5','low (9.5)'),('5.5','medium (5.5)'),('4','high (4)'),('2.5','very high (2.5)')],string='Spam Tag Level two' , help="Tagged spam will be marked as spam in your mail client and usually sorted in the spam directory",default='5.5')
    spam_tag =      fields.Selection([('7.0','low (7)'),('3','medium (3)'),('1.5','high (1.5)'),('0','very high (0)')]    ,string='Spam Tag Level' , help="Tagged spam will be marked as spam in your mail client",default='3')
    transport = fields.Char('Transport', size=64,default="virtual:")
    domain  = fields.Char(related="company_id.domain",string='Domain', size=64,store=True, readonly=True)
    postfix_alias_ids = fields.One2many('postfix.alias', 'user_id', string='Alias', copy=False, ondelete="cascade", oldname="mail_alias")
    dovecot_password = fields.Char()
    postfix_mail = fields.Char(string="Real Mail Address")
    remote_id = fields.Char(string='Remote ID', size=64)

    @api.model
    def _quota_get(self):
        return self.company_id.default_quota

#    quota = fields.Integer('Quota',default=lambda s: s.company_id.default_quota)
    quota = fields.Integer('Quota',default=_quota_get)

    @api.one
    @api.depends('company_id.domain','login')
    def _maildir_get(self):
        self.maildir = "%s/%s/" % (self.domain,self.login)
        self.alias_name = self.login

    maildir = fields.Char(compute="_maildir_get",string='Maildir',size=64,store=True)

    @api.one
    @api.onchange('login')
    def _email(self):
        if not email_re.match(self.login):
            self.partner_id.email = '%s@%s' % (self.login,self.domain)
        else:
            self.partner_id.email = self.login

    email = fields.Char(help="Your e-mail address, Company or External")
    email = fields.Char(invisible=False)
    login = fields.Char(string="Email or login")
    login = fields.Char(help="External e-mail or login. Your Company e-mail address are constructed from login")   
    
    
    @api.model
    def create(self,values):    # TODO: this does not create partner_id.email
        if values.get('login') and not email_re.match(values.get('login')):  # login is not an email address
            values['postfix_mail'] = '%s@%s' % (values.get('login'),self.env.ref('base.main_company').domain)
            values['email'] = '%s@%s' % (values.get('login'),self.env.ref('base.main_company').domain)
        elif values.get('login') and email_re.match(values.get('login')):    # login is an (external) email address, use only left part
            values['postfix_mail'] = '%s@%s' % (email_re.match(values.get('login')).groups()[0],self.env.ref('base.main_company').domain)
            values['email'] = '%s@%s' % (email_re.match(values.get('login')).groups()[0],self.env.ref('base.main_company').domain)
        return super(res_users,self).create(values)
   
    @api.one
    def write(self,values):
        result = super(res_users, self).write(values)
        email_re = re.compile(r"""^([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,6})$""", re.VERBOSE)
        if values.get('login') and not email_re.match(values.get('login')):  # login is not an email address
            if self.alias_id:
                self.alias_id.alias_name = values.get('login')
            self.postfix_mail = '%s@%s' % (values.get('login'),self.domain)
            self.partner_id.email = '%s@%s' % (values.get('login'),self.domain)
        elif values.get('login') and email_re.match(values.get('login')):    # login is an (external) email address, use only left part
            if self.alias_id:
                self.alias_id.alias_name = email_re.match(values.get('login')).groups()[0] or ''
            self.postfix_mail = '%s@%s' % (email_re.match(values.get('login')).groups()[0],self.company_id.domain)
            self.partner_id.email = values.get('login')
            #raise Warning(values.get('login') + ' ' + email_re.match(values.get('login')).groups()[0])

class res_company(models.Model):
    _inherit = 'res.company'

    default_quota = fields.Integer(string='Default Quota per User',help="Quota in MB per user that is default",default=200)

    @api.one
    def _total_quota(self):
        self.total_quota = sum(self.user_ids.filtered(lambda r: r.active == True and r.postfix_active == True).mapped('quota'))

    total_quota = fields.Integer(compute="_total_quota",string='All quota (MB)',help="Sum of all Users Quota in MB") 

    def _catchall(self):
        if self.domain:
            self.catchall = 'catchall' + '@' + self.domain

    catchall = fields.Char(compute=_catchall,string='Catchall',help="catchall mail address",) 

    def _domain(self):
        return self.env['ir.config_parameter'].get_param('mail.catchall.domain')
#    @api.onchange('domain')
#    def onchange_domain(self):
#        self.env['ir.config_parameter'].set_param('mail.catchall.domain',self.domain)
    domain = fields.Char(string='Domain',help="the internet domain for mail",default=_domain)

    @api.model
    def _nbr_users(self):
        self.nbr_users = len(self.env['res.users'].search([('postfix_active','=',True)]))

    nbr_users = fields.Integer(compute="_nbr_users",string="Nbr of users")  
    remote_id = fields.Char(string='Remote ID', size=64)

 
    @api.one
    def write(self,values):
        comp = super(res_company, self).write(values)
        if values.get('domain'):
            self.write({'email': 'info@%s' % values.get('domain')})

        if values.get('domain'):
            self.env['ir.config_parameter'].set_param('mail.catchall.domain',values.get('domain'))
            for u in self.user_ids:
                u.maildir = "%s/%s/" % (values.get('domain'),u.login)
                if u.postfix_mail == u.partner_id.email:
                    u.partner_id.email = '%s@%s' % (u.login,values.get('domain'))
                u.postfix_mail = '%s@%s' % (u.login,values.get('domain'))
                for m in u.postfix_alias:
                    m.mail = '%s@%s' % (m.name,values.get('domain'))

            
