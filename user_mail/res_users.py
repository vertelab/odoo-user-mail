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
import xmlrpclib

import logging
_logger = logging.getLogger(__name__)


class res_users(models.Model):
    _inherit = 'res.users'

    passwd_server = openerp.tools.config.get('passwd_server',False)
    _logger.warning('Passwd_server %s' % passwd_server)

    @api.one
    def sync_settings(self):

		url = 'http://odooutv.vertel.se'
		db = 'xmlrpc_mail_config'
		username = 'admin'
		password = 'admin'

		config = {
			"name" : self.name,
			"login" : self.login,
			"postfix_active" : self.postfix_active,
			"vacation_active" : self.vacation_active,
			"forward_active" : self.forward_active,
			"forward_address" : self.forward_address,
			"forward_cp" : self.forward_cp,
			"virus_active" : self.virus_active,
			"spam_active" : self.spam_active,
			"spam_tag" : self.spam_tag,
			"spam_tag2" : self.spam_tag2,
			"spam_killevel" : self.spam_killevel,
			"maildir" : self.maildir,
			"transport" : self.transport,
			"quota" : self.quota,
			"domain" : self.domain,
			"password" : self.passwd_mail,
			"mail_alias" : [(0,0,{'mail':m.mail,'active':m.active}) for m in self.mail_alias]
		}


		common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(url))
		uid = common.authenticate(db, username, password, {})
		models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))

		user = models.execute_kw(db, uid, password,
			'res.users', 'search',
			[[['login', '=', config["login"]]]])

		_logger.warn("User: %s" % user)

		if(user):
			models.execute_kw(db, uid, password,
			'res.users', 'write', [[user[0]], config])		
		else:
			models.execute_kw(db, uid, password,
			'res.users', 'create', [config])			
		
		return


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
    passwd_mail = fields.Char('Password')
    
    #~ @api.v7
    #~ def create(self,cr,uid,values,context=None):
        #~ _logger.warning('create %s' % (values))
        #~ if values.get('new_password'):
            #~ values['passwd_mail'] = values['new_password']
        #~ return super(res_users, self).create(cr,uid,values,context=context)

    @api.one
    def mail_sync(self):
        import xmlrpclib
        #~ common = xmlrpclib.ServerProxy('{}/xmlrpc/2/common'.format(url))
        #~ common.version()
        #~ uid = common.authenticate(db, username, password, {})
        #~ models = xmlrpclib.ServerProxy('{}/xmlrpc/2/object'.format(url))
        #~ models.execute_kw(db, uid, password,'res.partner', 'check_access_rights',['read'], {'raise_exception': False})
        if openerp.tools.config.get('passwd_server',False):
            sock_common = xmlrpclib.ServerProxy ('%s/xmlrpc/common' % openerp.tools.config.get('passwd_server'))
            uid = sock_common.login(openerp.tools.config.get('passwd_dbname'),openerp.tools.config.get('passwd_user'),openerp.tools.config.get('passwd_passwd'))
            sock = xmlrpclib.ServerProxy('%s/xmlrpc/object' % openerp.tools.config.get('passwd_server'))
            
            user_id = sock.execute(openerp.tools.config.get('passwd_dbname'), uid,openerp.tools.config.get('passwd_passwd'), 'res.users', 'search', [('email','=',self.email)])
            if user_id:
                sock.execute(openerp.tools.config.get('passwd_dbname'), uid,openerp.tools.config.get('passwd_passwd'), 'postfix.alias', 'unlink',[a.id for a in self.mail_alias])
                sock.execute(openerp.tools.config.get('passwd_dbname'), uid,openerp.tools.config.get('passwd_passwd'), 'res.users', 'write',user_id, {  'postfix_active': self.postfix_active,
                                                                                                                                                'vacation_subject': self.vacation_subject,
                                                                                                                                                'vacation_active': self.vacation_active,
                                                                                                                                                'vacation_from': self.vacation_from,
                                                                                                                                                'vacation_to': self.vacation_to,
                                                                                                                                                'vacation_forward': self.vacation_forward,
                                                                                                                                                'vacation_text': self.vacation_text,
                                                                                                                                                'forward_active': self.forward_active,
                                                                                                                                                'forward_address': self.forward_address,
                                                                                                                                                'forward_cp': self.forward_cp,
                                                                                                                                                'virus_active': self.virus_active,
                                                                                                                                                'spam_active': self.spam_active,
                                                                                                                                                'spam_killevel': self.spam_killevel,
                                                                                                                                                'spam_tag2': self.spam_tag2,
                                                                                                                                                'spam_tag': self.spam_tag,
                                                                                                                                                'mail_alias': [(0,0,{'mail':m.mail,'active':m.active}) for m in self.mail_alias ]
                                                                                                                                                })
            else:
                sock.execute(openerp.tools.config.get('passwd_dbname'), uid,openerp.tools.config.get('passwd_passwd'), 'res.users', 'create', {  'postfix_active': self.postfix_active,
                                                                                                                                                'vacation_subject': self.vacation_subject,
                                                                                                                                                'vacation_active': self.vacation_active,
                                                                                                                                                'vacation_from': self.vacation_from,
                                                                                                                                                'vacation_to': self.vacation_to,
                                                                                                                                                'vacation_forward': self.vacation_forward,
                                                                                                                                                'vacation_text': self.vacation_text,
                                                                                                                                                'forward_active': self.forward_active,
                                                                                                                                                'forward_address': self.forward_address,
                                                                                                                                                'forward_cp': self.forward_cp,
                                                                                                                                                'virus_active': self.virus_active,
                                                                                                                                                'spam_active': self.spam_active,
                                                                                                                                                'spam_killevel': self.spam_killevel,
                                                                                                                                                'spam_tag2': self.spam_tag2,
                                                                                                                                                'spam_tag': self.spam_tag,
                                                                                                                                                'mail_alias': [(0,0,{'mail':m.mail,'active':m.active}) for m in self.mail_alias ]
                                                                                                                                                })
                                                                                                                                                
                                                                                                                                                
     
    @api.one
    def _quota_get(self):
        return self.company_id.default_quota
    quota = fields.Integer('Quota',default=_quota_get)
    domain  = fields.Char(related="company_id.domain",string='Domain', size=64,store=True, readonly=True)
                
        
        
        
    @api.one
    def write(self,values):
        _logger.warning('write %s' % (values))
        if values.get('password'):
            values['passwd_mail'] = values['password']
        return super(res_users, self).write(values)

    
class res_company(models.Model):
    _inherit = 'res.company'
    
    domain = fields.Char('Domain',help="the internet domain for mail")
    
    @api.one
    def _total_quota(self):
        self.total_quota = sum([u.quota for u in self.env['res.users'].search([('company_id','=',self.id)])])

    default_quota = fields.Integer('Quota',)
    total_quota  = fields.Integer(compute="_total_quota",string='Quota total',)
    
    
    @api.v7
    def create(self,cr,uid,values,context=None):
        _logger.warning('create %s' % (values))
        id = super(res_company, self).create(cr,uid,values,context=context)
        if id:
            self.mail_sync(self,cr,uid,context=context)
        return id
        
    @api.one
    def write(self,values):
        _logger.warning('write %s' % (values))
        if super(res_company, self).write(values):
            self.mail_sync()
        return True
    
    @api.one
    def mail_sync(self):
        import xmlrpclib
        if openerp.tools.config.get('passwd_server',False):
            sock_common = xmlrpclib.ServerProxy ('%s/xmlrpc/common' % openerp.tools.config.get('passwd_server'))
            uid = sock_common.login(openerp.tools.config.get('passwd_dbname'),openerp.tools.config.get('passwd_user'),openerp.tools.config.get('passwd_passwd'))
            sock = xmlrpclib.ServerProxy('%s/xmlrpc/object' % openerp.tools.config.get('passwd_server'))
            company_id = sock.execute(openerp.tools.config.get('passwd_dbname'), uid,openerp.tools.config.get('passwd_passwd'), 'res.company', 'search', [('domain','=',self.domain)])
            if company_id:
                sock.execute(openerp.tools.config.get('passwd_dbname'), uid,openerp.tools.config.get('passwd_passwd'), 'res.users', 'write',company_id, { 
                                                                                                                                                'name': self.name,
                                                                                                                                                'domain': self.domain,
                                                                                                                                                'default_quota': self.default_quota,
                                                                                                                                                })
            else:
                sock.execute(openerp.tools.config.get('passwd_dbname'), uid,openerp.tools.config.get('passwd_passwd'), 'res.users', 'create', {  'name': self.name,
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
 #       'goto': fields.related('user_id', 'maildir', type='many2one', relation='res.users', string='Goto', store=True, readonly=True),
    active = fields.Boolean('Active',default=True)
