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
import uuid
from passlib.hash import sha512_crypt

SYNCSERVER = None

class sync_settings_wizard(models.TransientModel):
    _inherit = "user.mail.sync.wizard"

    def default_user_ids(self):
        return self.env['res.users'].browse(self._context.get('active_ids'))

    @api.one
    def sync_settings(self):
        companies = set()
        for user in self.default_user_ids():
            user.sync_settings(self.gen_pw)
            companies.add(user.company_id)
        for c in companies:
            pass
            c.sync_settings()

        return {}

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
    
    def generate_password(self):
        alphabet = string.digits + string.letters + '+_-!@#$%&*()'
        return ''.join(alphabet[ord(os.urandom(1)) % len(alphabet)] for i in range(int(self._get_param('pw_length',13))))

    def generate_dovecot_sha512(self, pw):
        return sha512_crypt.encrypt(pw)


    @api.one
    def sync_settings(self, generate_password=False):  
        SYNCSERVER = Sync2server(self)

        record = {f:self.read()[0][f] for f in [
                                              'name', 'login', 'dovecot_password',
                                              'postfix_active',
                                              'vacation_subject','vacation_active','vacation_from',
                                              'vacation_to','vacation_forward','vacation_text',
                                              'forward_active','forward_address','forward_cp',
                                              'virus_active',
                                              'spam_active','spam_killevel','spam_tag2','spam_tag',
                                              'transport','quota']}

        if generate_password:
            record['new_password'] = self.generate_password()
            record['dovecot_password'] = self.generate_dovecot_sha512(record['new_password'])
            self.env['res.users.password'].update_pw(self.id, record['new_password'])

        record['mail_alias'] = [(0,0,{'mail':m.mail,'active':m.active}) for m in self.mail_alias]
        remote_user_id = SYNCSERVER.search(self._name,[('login','=',self.login)])

        if remote_user_id:
            SYNCSERVER.unlink('postfix.alias', SYNCSERVER.search('postfix.alias',[('user_id','=',remote_user_id)]))
            SYNCSERVER.write(self._name, remote_user_id, record)
        else:
            SYNCSERVER.create(self._name, record)
    
    @api.one
    def write(self,values):
        passwd = values.get('password') or values.get('new_password')
        if passwd:
            self.dovecot_password = self.generate_dovecot_sha512(passwd)
            values['dovecot_password'] = self.dovecot_password            
            #self.env['res.users.password'].update_pw(self.id, passwd)

        SYNCSERVER = Sync2server(self)
        remote_user_id = SYNCSERVER.search(self._name,[('login','=',self.login)])

        if remote_user_id:
            SYNCSERVER.write(self._name,remote_user_id, values)

        return super(res_users, self).write(values)

    @api.model
    def create(self, values):
        passwd = values.get('password') or values.get('new_password')
        if passwd:
            values['dovecot_password'] = self.generate_dovecot_sha512(passwd)         
            #self.env['res.users.password'].update_pw(self.id, passwd)

        #pass this context to auth_signup create-function to prevent it from sending reset password emails 
        context = {'no_reset_password' : True}
           
        user = super(res_users, self).create(values, context=context)

        return user

    @api.one
    def unlink(self):
        SYNCSERVER = Sync2server(self)

        user_id = self.env['res.users'].search([('login','=',self.login)]).id
        postfix_alias_id = self.env['postfix.alias'].search([('user_id', '=', user_id)]).unlink()
        #only needed if deleting a user with recently changed password
        self.env['change.password.wizard'].search([('user_ids', '=', self.id)]).unlink()
        self.env['change.password.user'].search([('user_id', '=', self.id)]).unlink()

        remote_user = SYNCSERVER.remote_user(self)
        if remote_user:
            SYNCSERVER.unlink(self._name, remote_user)

        return super(res_users, self).unlink()

class res_company(models.Model):
    _inherit = 'res.company'
  
    def _get_param(self,param,value):
        if not self.env['ir.config_parameter'].get_param(param):
            self.env['ir.config_parameter'].set_param(param,value)
        return self.env['ir.config_parameter'].get_param(param)

    def generateUUID(self):
        return uuid.uuid4()
                
    @api.one
    def write(self,values):
        _logger.warn("\nIN WRITE-----------")
        values['remote_id'] = self.generateUUID()
        super(res_company, self).write(values)
        _logger.warn("\nVALUES IS IN WRITE: %s" % values)
        self.sync_settings()

        if values.get('domain',False) and self.id == self.env.ref('base.main_company').id:  # Create mailservers when its a main company and not mainserver
            self.env['ir.config_parameter'].set_param('mail.catchall.domain',values.get('domain'))
            password = self._createcatchall()
            self._smtpserver(password)
            self._imapserver(password)   

    @api.one
    def unlink(self):
        SYNCSERVER = Sync2server(self)

        remote_company = SYNCSERVER.remote_company(self)

        if remote_company:
            SYNCSERVER.unlink(self._name, remote_company) 
             
        super(res_company, self).unlink()


    @api.model
    def create(self,values):
        _logger.warn("\nIN WRITE-----------")
        SYNCSERVER = Sync2server(self)

        values['remote_id'] = self.generateUUID()
        _logger.warn("\nVALUES IS IN WRITE: %s" % values)
        company = super(res_company, self).create(values)  

        if company:
            remote_company_id = company.sync_settings()

            if values.get('domain',False) and self.id == self.env.ref('base.main_company').id:  # Create mailservers when its a main company and not mainserver
                self.env['ir.config_parameter'].set_param('mail.catchall.domain',values.get('domain'))    
                password = company._createcatchall()
                self._smtpserver(password)
                self._imapserver(password)        
          
        return company

    @api.one
    def sync_settings(self):  
        SYNCSERVER = Sync2server(self) 

        record = {f:self.read()[0][f] for f in  ['name','domain','catchall','default_quota', 'email', 'remote_id']}
        remote_company_id = SYNCSERVER.remote_company(self)
        
        if remote_company_id:
            SYNCSERVER.write(self._name, remote_company_id, record)
            return remote_company_id
        else:
            return SYNCSERVER.create(self._name, record)
        
    @api.one
    def _createcatchall(self):
        SYNCSERVER = Sync2server(self)
        new_pw = self.env['res.users'].generate_password()

        record = {
            'new_password': new_pw,
            'name': 'Catchall', 
            'login': self.catchall,
            'postfix_active': True, 
            'email': self.catchall, 
            'mail_alias': [(0,0,{'mail': '@%s' % self.domain,'active':True})],
            'company_ids': [self.id],
            'company_id': self.id,
            'dovecot_password': self.env['res.users'].generate_dovecot_sha512(new_pw)
        }

        SYNCSERVER.create('res.users', record)            

        return new_pw

    def _smtpserver(self,password):    
        record = {
            'name':            'smtp',
            'smtp_host':       get_config('smtp_server','SMTP-server missing!'),
            'smtp_port':       get_config('smtp_port','SMTP-port missing!'), 
            'smtp_encryption': get_config('smtp_encryption','SMTP-encryption missing!'),
            'smtp_user':       self.catchall,
            'smtp_pass':       password,
            'sequence':        10,
        }

        smtp = None

        try:
            smtp = self.env.ref('base.ir_mail_server_localhost0')
        except Exception, e:
            pass    

        if smtp:
            smtp.write(record)
        else:
            self.env['ir.mail_server'].create(record)

    def _imapserver(self,passwd):    
        record = {
                'name': 'imap',
                'server': get_config('imap_host','IMAP name missing!'),
                'port':   get_config('imap_port','IMAP port missing!'),
                'is_ssl': True,
                'type': 'imap',
                'active': True,
                'state': 'done',
                'user': self.catchall,
                'password': passwd, 
        }
        imap = self.env['fetchmail.server'].search([],order='priority desc',limit=1)
        if not imap:
            self.env['fetchmail.server'].create(record)
        else:
            imap.write(record)


def get_config(param,msg):
    value = openerp.tools.config.get(param,False)
    if not value:
        raise Warning(_("%s (%s in /etc/odoo/openerp-server.conf)" % (msg,param)))
    return value

class Sync2server():
    def __init__(self, model):
        
        self.passwd_server = get_config('passwd_server','Server uri is missing!')
        self.passwd_dbname = get_config('passwd_dbname','Databasename is missing')
        self.passwd_user   = get_config('passwd_user','Username is missing')
        self.passwd_passwd = get_config('passwd_passwd','Password is missing')

        try:
            self.sock_common = xmlrpclib.ServerProxy('%s/xmlrpc/common' % self.passwd_server)
            self.uid = self.sock_common.login(self.passwd_dbname, self.passwd_user, self.passwd_passwd)
            self.sock = xmlrpclib.ServerProxy('%s/xmlrpc/object' % self.passwd_server, allow_none=True)
        except xmlrpclib.Error as err:
            raise Warning(_("%s (server %s, db %s, user %s, pw %s)" % (err, self.passwd_server, self.passwd_dbname, self.passwd_user, self.passwd_passwd)))
            
    def search(self,model,domain):     
        return self.sock.execute(self.passwd_dbname, self.uid, self.passwd_passwd,model, 'search', domain)

    def write(self,model,id,values):    
        return self.sock.execute(self.passwd_dbname, self.uid, self.passwd_passwd, model, 'write', id, values)

    def create(self,model,values):
        return self.sock.execute(self.passwd_dbname, self.uid, self.passwd_passwd,model,'create', values)

    def unlink(self,model,ids):
        return self.sock.execute(self.passwd_dbname, self.uid, self.passwd_passwd, model, 'unlink',ids)

    def remote_company(self, company):
        # User company.remote_id for this company
        remote_company = self.search('res.company',[('remote_id','=',company.remote_id)])          
        if remote_company:
            return remote_company[0]
        else: 
            return None

    def remote_user(self,user):
        # User user.remote_id for this user
        remote_user = self.search('res.users',[('login','=',user.login)])
        if remote_user:
            return remote_user[0]
        else: 
            return None

    def remote_catchall(self, catchall):
        remote_catchall = self.search('res.users',[('login','=',catchall)])
        if remote_catchall:
            return remote_catchall[0]
        else: 
            return None

