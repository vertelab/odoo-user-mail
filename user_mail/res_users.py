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
import openerp.tools
import xmlrpclib
from openerp.exceptions import Warning
import os, string

import logging
_logger = logging.getLogger(__name__)

class sync_settings_wizard(models.TransientModel):
    _name = "user.mail.sync.wizard"

    def default_user_ids(self):
        return self.env['res.users'].browse(self._context.get('active_ids'))

    gen_pw = fields.Boolean(string="generate_password")

    @api.one
    def sync_settings(self):
        for user in self.env['res.users'].browse(self._context.get('active_ids', [])):
            user.sync_settings(self.gen_pw)

        return {}

class res_users(models.Model):
    _inherit = 'res.users'    

    @api.one
    def _maildir_get(self):
        self.maildir = "%s/%s/" % (self.company_id.domain,self.user_email)

    postfix_active = fields.Boolean('Active',default=False)
    #      'full_email': fields.function(_full_email,string='Full Email',type="char",size=64,store=True,select=1),
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
    maildir = fields.Char(compute="_maildir_get",string='Maildir',size=64,store=True,select=1)
    transport = fields.Char('Transport', size=64,default="virtual:")

    @api.one
    def _quota_get(self):
        return self.company_id.default_quota
    quota = fields.Integer('Quota',default=_quota_get)
    domain  = fields.Char(related="company_id.domain",string='Domain', size=64,store=True, readonly=True)
    #        'mail': fields.char('Mail', size=64,),
    #        'mail_active': fields.boolean('Active'),
    mail_alias = fields.One2many('postfix.alias', 'user_id', string='Alias', copy=True)

    @api.one
    def _passwd_mail(self):
        pw = self.env['res.users.password'].search([('user_id','=',self.id)])
        self.passwd_mail = pw and pw.passwd_mail or _('None')

    passwd_mail = fields.Char(compute=_passwd_mail,string='Password')
    
    def _get_param(self,param,value):
        if not self.env['ir.config_parameter'].get_param(param):
            self.env['ir.config_parameter'].set_param(param,value)
        return self.env['ir.config_parameter'].get_param(param)
    
    # Default forward till företagets catchall-adress
    # Kontrollera att mailalias bara är knuten till rätt domän
    def generate_password(self):
        alphabet = string.digits + string.letters + '+_-!@#$%&*()'
        return ''.join(alphabet[ord(os.urandom(1)) % len(alphabet)] for i in range(int(self._get_param('pw_length',13))))


    @api.one
    def sync_settings(self, generate_password=False):     
  
        passwd_server = openerp.tools.config.get('passwd_server',False)
        passwd_dbname = openerp.tools.config.get('passwd_dbname',False)
        passwd_user   = openerp.tools.config.get('passwd_user',False)
        passwd_passwd = openerp.tools.config.get('passwd_passwd',False)

        if not passwd_passwd:
            raise Warning(_("Password is missing! (passwd_passwd in openerp-server.conf)"))
        if not passwd_server:
            raise Warning(_("Server uri is missing! (passwd_server in openerp-server.conf)"))
        if not passwd_dbname:
            raise Warning(_("Database name is missing! (passwd_dbname in openerp-server.conf)"))
        if not passwd_user:
            raise Warning(_("Username is missing! (passwd_user in openerp-server.conf)"))

        FIELDS = ['name', 'login',
                  'postfix_active',
                  'vacation_subject','vacation_active','vacation_from',
                  'vacation_to','vacation_forward','vacation_text',
                  'forward_active','forward_address','forward_cp',
                  'virus_active',
                  'spam_active','spam_killevel','spam_tag2','spam_tag',
                  'transport','quota']

        if generate_password:
            self.env['res.users.password'].update_pw(self.id,self.generate_password())

        record = {}
        for f in FIELDS:            
            record[f] = eval('self.%s' % f)
        record['new_password'] = self.passwd_mail
        record['mail_alias'] = [(0,0,{'mail':m.mail,'active':m.active}) for m in self.mail_alias ]

        
        try:
            sock_common = xmlrpclib.ServerProxy('%s/xmlrpc/common' % passwd_server)              
            uid = sock_common.login(passwd_dbname, passwd_user, passwd_passwd)
            sock = xmlrpclib.ServerProxy('%s/xmlrpc/object' % passwd_server)
        except xmlrpclib.Error as err:
            raise Warning(_("%s" % err))

        user_id = sock.execute(passwd_dbname, uid,passwd_passwd,'res.users', 'search', [('login','=',self.login)])

        if user_id:
            sock.execute(passwd_dbname,uid,passwd_passwd,'postfix.alias', 'unlink',[a.id for a in self.mail_alias])
            sock.execute(passwd_dbname, uid,passwd_passwd, 'res.users', 'write',user_id, record)
        else:
            sock.execute(passwd_dbname,uid,passwd_passwd,'res.users', 'create',record)


    
    @api.one
    def write(self,values):
        _logger.warning('write %s' % (values))
        if values.get('new_password',False):
           self.env['res.users.password'].update_pw(self.id,values.get('new_password'))
        return super(res_users, self).write(values)
# Användarfall
# 1) Skapa en ny användare med ett lösenord backoffice, synka kontrollera att rätt lösenord är synkat (logga in på odooutv) och titta på passwd_mail (löseordet i klartext) - fungerar som smort, men det går inte att se lösenordet som vanlig användare
# 2) Aktivera självregistrering, kontrollera det synkade lösenordet
# 3) Administratören byter lösenord på en användare - fungerar utmärkt
# 4) Användaren byter själv - Inte möjligt




    #~ @api.v7
    #~ def create(self,cr,uid,values,context=None):
        #~ _logger.warning('create %s' % (values))
        #~ if values.get('new_password'):
            #~ values['passwd_mail'] = values['new_password']
        #~ return super(res_users, self).create(cr,uid,values,context=context)

class users_password(models.TransientModel):
    _name = "res.users.password"
    
    user_id = fields.Many2one(comodel_name='res.users',string="User")
    passwd_mail = fields.Char('Password')

    def update_pw(self,user_id,pw):
        user = self.search([('user_id','=',user_id)])

        if user:
            user.write({'passwd_mail': pw})
        else:
            self.create({'user_id': user_id, 'passwd_mail': pw})
            
class res_company(models.Model):
    _inherit = 'res.company'

    passwd_server = openerp.tools.config.get('passwd_server',False)
    passwd_dbname = openerp.tools.config.get('passwd_dbname',False)
    passwd_user   = openerp.tools.config.get('passwd_user',False)
    passwd_passwd = openerp.tools.config.get('passwd_passwd',False)

    if not passwd_passwd:
        raise Warning(_("Password is missing! (passwd_passwd in openerp-server.conf)"))
    if not passwd_server:
        raise Warning(_("Server uri is missing! (passwd_server in openerp-server.conf)"))
    if not passwd_dbname:
        raise Warning(_("Database name is missing! (passwd_dbname in openerp-server.conf)"))
    if not passwd_user:
        raise Warning(_("Username is missing! (passwd_user in openerp-server.conf)"))
    
    def _get_param(self,param,value):
        if not self.env['ir.config_parameter'].get_param(param):
            self.env['ir.config_parameter'].set_param(param,value)
        return self.env['ir.config_parameter'].get_param(param)
    
    def _domain(self):
        self.domain = self.env['ir.config_parameter'].get_param('mail.catchall.domain') or ''
    domain = fields.Char(compute=_domain,string='Domain',help="the internet domain for mail",default=_domain)

    def _catchall(self):
        self.catchall = self.env['ir.config_parameter'].get_param('mail.catchall.alias') or 'catchall' + '@' + self.domain
    catchall = fields.Char(compute=_catchall,string='Catchall',help="catchall mail address",)   
    
    @api.one
    def _total_quota(self):
        self.total_quota = sum([u.quota for u in self.env['res.users'].search([('company_id','=',self.id)])])

    default_quota = fields.Integer('Quota',)
    total_quota  = fields.Integer(compute="_total_quota",string='Quota total')    
    
    @api.v7
    def create(self,cr,uid,values,context=None):
        _logger.warning('create %s' % (values))
        # Skapa catchall@domain-address, uppdatera/skapa ingående/utgående server använd catchall-adressen som id 
        id = super(res_company, self).create(cr,uid,values,context=context)
        if id:
            self.mail_sync(self,cr,uid,context=context)
        return id
        
    
    @api.one
    def write(self,values):
        _logger.warning('write %s' % (values))
        
        if values.get('domain',False) and self.id == self.ref('base.main_company'):
            self.env['ir.config_parameter'].set_param('mail.catchall.domain',values.get('domain'))

            smtp_server = openerp.tools.config.get('smtp_server',False)
            smtp_port = openerp.tools.config.get('smtp_port',False)
            smtp_encryption = openerp.tools.config.get('smtp_encryption',False)
            
            if not smtp_server:
                raise Warning(_("SMTP-server missing! (smtp_server in openerp-server.conf)"))
            if not smtp_port:
                raise Warning(_("SMTP-port missing! (smtp_port in openerp-server.conf)"))
            if not smtp_encryption:
                raise Warning(_("SMTP-encryption missing! (smtp_encryption in openerp-server.conf, [none,starttls,ssl])"))

            alphabet = string.digits + string.letters + '+_-!@#$%&*()'
            smtp_pass = ''.join(alphabet[ord(os.urandom(1)) % len(alphabet)] for i in range(int(self._get_param('pw_length',13))))

            smtp = self.env['ir.mail_server'].ref('base.ir_mail_server_localhost0') or self.env['ir.mail_server'].create({
                'name': 'smtp','smtp_host': smtp_server,'smtp_port': smtp_port, 'smtp_encryption': smtp_encryption})

            smtp.write({'name': 'smtp','smtp_host': smtp_server,'smtp_port': smtp_port, 'smtp_encryption': smtp_encryption,
                        'smtp_user': self.catchall, 'smtp_pass': smtp_pass})

            self.sync_catchall()
            # lägg upp / ändra kontot catchall-användaren i remote res.users
            
            # skapa / ändra imap-server
            
        if super(res_company, self).write(values):
            return True
            #self.mail_sync()
        return True

    @api.one
    def sync_catchall(self):

        sock_common = xmlrpclib.ServerProxy ('%s/xmlrpc/common' % self.passwd_server)
        uid = sock_common.login(self.passwd_dbname, self.passwd_user, self.passwd_passwd)
        sock = xmlrpclib.ServerProxy('%s/xmlrpc/object' % self.passwd_server)

        catchall_user_id = sock.execute(self.passwd_dbname, uid, self.passwd_passwd,
         'res.users', 'search', [('login', '=', self.catchall)])

        _logger.warn("Got the catchall_id: %s" % catchall_user_id)

        if catchall_user_id:
            sock.execute(self.passwd_dbname, uid, self.passwd_passwd, 'res.users', 'write', catchall_user_id, self.catchall)
        else:
            sock.execute(self.passwd_dbname, uid, self.passwd_passwd,'res.users', 'create', {"name" : "catchall",
                                                                                             "login" : self.catchall,
                                                                                             "postfix_active" : 1,
                                                                                             "new_password" : self.env['res.users'].generate_password()})

        return
    
    @api.one
    def mail_sync(self):

        sock_common = xmlrpclib.ServerProxy ('%s/xmlrpc/common' % passwd_server)
        uid = sock_common.login(passwd_dbname, passwd_user, passwd_passwd)
        sock = xmlrpclib.ServerProxy('%s/xmlrpc/object' % passwd_server)

        company_id = sock.execute(passwd_dbname, uid, passwd_passwd, 'res.company', 'search', [('domain','=',self.domain)])

        if company_id:
            sock.execute(passwd_dbname, uid, passwd_passwd, 'res.users', 'write',company_id, { 
                                                                                            'name': self.name,
                                                                                            'domain': self.domain,
                                                                                            'default_quota': self.default_quota,
                                                                                            })
        else:
            sock.execute(passwd_dbname, uid, passwd_passwd, 'res.users', 'create', {'name': self.name,
                                                                                    'domain': self.domain,
                                                                                    'default_quota': self.default_quota,
                                                                                    })                                                                                                                     
                                                                                                                                                
    
class postfix_vacation_notification(models.Model):
    _name = 'postfix.vacation_notification'
    user_id = fields.Many2one('res.users','User', required=True,)
    notified = fields.Char('Notified',size=64,select=1)
    date = fields.Date('Date',default=fields.Date.context_today)
    
class postfix_alias(models.Model):
    _name = 'postfix.alias'
    user_id = fields.Many2one('res.users','User', required=True,)
    mail    = fields.Char('Mail', size=64, help="Mail as <user>@<domain>, if you are using a foreign domain, make sure that this domain are handled by the same mailserver")
    # concatenate with domain from res.company 
 #       'goto': fields.related('user_id', 'maildir', type='many2one', relation='res.users', string='Goto', store=True, readonly=True),
    active = fields.Boolean('Active',default=True)
