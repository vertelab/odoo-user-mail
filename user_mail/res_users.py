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

SYNCSERVER = None

class sync_settings_wizard(models.TransientModel):
    _name = "user.mail.sync.wizard"

    def default_user_ids(self):
        return self.env['res.users'].browse(self._context.get('active_ids'))

    gen_pw = fields.Boolean(string="generate_password")

    @api.one
    def sync_settings(self):
        companies = set()
        for user in self.default_user_ids():
            user.sync_settings(self.gen_pw)
            companies.add(user.company_id)
        for c in companies:
            c.sync_settings()

        return {}

class postfix_vacation_notification(models.Model):
    _name = 'postfix.vacation_notification'
    #could not install because of the relation to user_id (postfix.alias has the same relation only one is allowed?)
    #user_id = fields.Many2one('res.users','User', required=True,)
    notified = fields.Char('Notified',size=64,select=1)
    date = fields.Date('Date',default=fields.Date.context_today)
    
class postfix_alias(models.Model):
    _name = 'postfix.alias'
    user_id = fields.Many2one('res.users',ondelete="set null", required=True,)
    mail    = fields.Char('Mail', size=64, help="Mail as <user>@<domain>, if you are using a foreign domain, make sure that this domain are handled by the same mailserver")
    # concatenate with domain from res.company 
 #       'goto': fields.related('user_id', 'maildir', type='many2one', relation='res.users', string='Goto', store=True, readonly=True),
    active = fields.Boolean('Active',default=True)


class res_users(models.Model):
    _inherit = 'res.users' 
 
    @api.one 
    @api.depends('company_id.domain','login')
    def _maildir_get(self):
#        self.maildir = "%s/%s/" % (self.company_id.domain,self.login)
        self.maildir = "%s/%s/" % (self.company_id.domain,self.login)

    postfix_active = fields.Boolean('Active',default=False)
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
    domain  = fields.Char(related="company_id.domain",string='Domain', size=64,store=True, readonly=True)
    mail_alias = fields.One2many('postfix.alias', 'user_id', string='Alias', copy=True)
    dovecot_password = fields.Char()

    @api.one
    def _quota_get(self):
        return self.company_id.default_quota
    quota = fields.Integer('Quota',default=_quota_get)

    @api.one
    def _passwd_mail(self):
        pw = self.env['res.users.password'].search([('user_id','=',self.id)])
        self.passwd_mail = pw and pw.passwd_mail or _('N/A')

    passwd_mail = fields.Char(compute=_passwd_mail,string='Password')
    
    def _get_param(self,param,value):
        if not self.env['ir.config_parameter'].get_param(param):
            self.env['ir.config_parameter'].set_param(param,value)
        return self.env['ir.config_parameter'].get_param(param)
    
    def generate_password(self):
        alphabet = string.digits + string.letters + '+_-!@#$%&*()'
        return ''.join(alphabet[ord(os.urandom(1)) % len(alphabet)] for i in range(int(self._get_param('pw_length',13))))

    def mainserver(self):
        # If local/remote database has the same name we asume its the same database / the mainserver
        return self.env.cr.dbname == get_config("passwd_dbname", "Database name is missing!")


    @api.one
    def sync_settings(self, generate_password=False):     
        global SYNCSERVER
        #if not SYNCSERVER:
        SYNCSERVER = Sync2server(self.env.cr.dbname, self, self.mainserver())

        record = {f:self.read()[0][f] for f in  [
                                              'name', 'login',
                                              'postfix_active',
                                              'vacation_subject','vacation_active','vacation_from',
                                              'vacation_to','vacation_forward','vacation_text',
                                              'forward_active','forward_address','forward_cp',
                                              'virus_active',
                                              'spam_active','spam_killevel','spam_tag2','spam_tag',
                                              'transport','quota']}

        if generate_password:
            record['new_password'] = self.generate_password()
            self.env['res.users.password'].update_pw(self.id, record['new_password'])

        record['mail_alias'] = [(0,0,{'mail':m.mail,'active':m.active}) for m in self.mail_alias ]

        remote_user_id = SYNCSERVER.search(self._name,[('login','=',self.login)], self.mainserver())

        if remote_user_id:
            SYNCSERVER.unlink('postfix.alias', SYNCSERVER.search('postfix.alias',[('user_id','=',remote_user_id)]), self.mainserver())
            SYNCSERVER.write(self._name,remote_user_id,record, self.mainserver())
        else:
            SYNCSERVER.create(self._name,record, self.mainserver())
    
    @api.one
    def write(self,values):
        if values.get('password',False):

            self.env['res.users.password'].update_pw(self.id, values['password'])
            global SYNCSERVER

            SYNCSERVER = Sync2server(self.env.cr.dbname, self, self.mainserver())
            remote_user_id = SYNCSERVER.search(self._name,[('login','=',self.login)], self.mainserver())

            if remote_user_id:
                SYNCSERVER.write(self._name,remote_user_id,{'password': values['password']}, self.mainserver())
            else:
                SYNCSERVER.create(self._name,{'password': values['password']}, self.mainserver())

        return super(res_users, self).write(values)


    def unlink(self, cr, uid, ids, context=None):
        postfix_alias_ids = self.pool.get('postfix.alias').search(cr, uid, [('user_id', '=', ids)], offset=0, limit=None, order=None, context=None)    
        self.pool.get('postfix.alias').unlink(cr, uid, postfix_alias_ids, context)
        return super(res_users, self).unlink(cr, uid, ids, context)


class users_password(models.TransientModel):
    _name = "res.users.password"
    
    user_id = fields.Many2one(comodel_name='res.users',string="User")
    passwd_mail = fields.Char('Password')

    def update_pw(self,user_id,pw):
        user = self.search([('user_id','=',user_id)])
        if user:
            user.passwd_mail = pw
        else:
            self.create({'user_id': user_id, 'passwd_mail': pw})
        return pw
            
class res_company(models.Model):
    _inherit = 'res.company'
  
    def _get_param(self,param,value):
        if not self.env['ir.config_parameter'].get_param(param):
            self.env['ir.config_parameter'].set_param(param,value)
        return self.env['ir.config_parameter'].get_param(param)

    @api.one
    def _domain(self):
        self.domain = self.env['ir.config_parameter'].get_param('mail.catchall.domain') or ''
    domain = fields.Char(string='Domain',help="the internet domain for mail",default=_domain)

    @api.one
    def _catchall(self):
        self.catchall = 'catchall' + '@' + self.domain
    catchall = fields.Char(compute=_catchall,string='Catchall',help="catchall mail address",)   
    
    @api.one
    def _total_quota(self):
        self.total_quota = sum([u.quota for u in self.env['res.users'].search([('company_id','=',self.id)])])

    default_quota = fields.Integer('Quota',)
    total_quota = fields.Integer(compute="_total_quota",string='Quota total')    

    remote_id = fields.Char(string='Remote ID', size=64)

    def mainserver(self):
        # If local/remote database has the same name we asume its the same database / the mainserver
        return self.env.cr.dbname == get_config("passwd_dbname", "Database name is missing!")

    def generateUUID(self):
        return uuid.uuid4()

                
    @api.one
    def Xwrite(self,values):
        global SYNCSERVER
        #if not SYNCSERVER:
        SYNCSERVER = Sync2server(self.env.cr.dbname, self, self.mainserver())

        super(res_company, self).write(values)
        remote_company_id = self.sync_settings()

        if self.mainserver():
            self._createcatchall()  # On mainserver all companies should have a catchall-user

        if values.get('domain',False) and self.id == self.env.ref('base.main_company').id:  # Create mailservers when its a main company and not mainserver
            self.env['ir.config_parameter'].set_param('mail.catchall.domain',values.get('domain'))

            if not self.mainserver():
                password = self._synccatchall(remote_company_id)
                self._smtpserver(password)
                self._imapserver(password)
            else:
                self._createcatchall()        


    @api.one
    def unlink(self):
        global SYNCSERVER
        #if not SYNCSERVER:
        SYNCSERVER = Sync2server(self.env.cr.dbname, self, self.mainserver())

        if self.mainserver():
            self.env['res.users'].search([('login','=',self.catchall)]).unlink()
        else:
            remote_company = SYNCSERVER.remote_company(self, self.mainserver())
            if remote_company:
                SYNCSERVER.unlink('res.company',remote_company, self.mainserver())            
        super(res_company, self).unlink()


    @api.model
    def create(self,values):
        #if not SYNCSERVER:
        SYNCSERVER = Sync2server(self.env.cr.dbname, self, self.mainserver())

        if not self.mainserver():
            values['remote_id'] = self.generateUUID()

        company = super(res_company, self).create(values)  

        if company:
            remote_company_id = company.sync_settings()
            if self.mainserver():
                company._createcatchall()  # On mainserver all companies should have a catchall-user            
          
        return company

    @api.one
    def sync_settings(self):  
        global SYNCSERVER
        #if not SYNCSERVER:
        SYNCSERVER = Sync2server(self.env.cr.dbname, self, self.mainserver())

        if not self.mainserver():
            record = {f:self.read()[0][f] for f in  ['name','domain','catchall','default_quota', 'email', 'remote_id']}
            remote_company_id = SYNCSERVER.remote_company(self, self.mainserver())

            if remote_company_id:

                SYNCSERVER.write(self._name,remote_company_id, record, self.mainserver())
                return remote_company_id
            else:
                return SYNCSERVER.create(self._name, record, self.mainserver())
        


    def _synccatchall(self,remote_company_id):
        #if not SYNCSERVER:
        SYNCSERVER = Sync2server(self.env.cr.dbname, self, self.mainserver())

        record = {
            'new_password': self.env['res.users'].generate_password(),
            'login': self.catchall,  # mail-module does not like not using this attribute
        }

        if not self.mainserver():
            remote_user_id = SYNCSERVER.search('res.users',[('login','=',self.catchall)], self.mainserver()) #TODO: put a remote id here to update catchall

            if remote_user_id:
                remote_user_id = remote_user_id[0]
                SYNCSERVER.write('res.users',remote_user_id, record, self.mainserver())
            else:
                SYNCSERVER.create('res.users', record, self.mainserver())

            return record['new_password']  # Return the password for temporary use

    def _createcatchall(self):

        record = {
            'new_password': self.env['res.users'].generate_password(),
            'name': 'Catchall', 
            'login': self.catchall,
            'postfix_active': True, 
            'email': self.catchall, 
            'mail_alias': [(0,0,{'mail': '@%s' % self.domain,'active':True})],
            'company_ids': [self.id],
            'company_id': self.id,
        }

        ca_user = self.env['res.users'].search([('login','=',self.catchall)],limit=1)
        if not ca_user:  

            context = {'no_reset_password' : True}
            recs = self.with_context(context)

            user_id = recs.env['res.users'].create(record).id
            self.env['res.users.password'].update_pw(user_id, record['new_password'])

        else:
            self.env['postfix.alias'].search([('user_id','=',ca_user.id)]).unlink()
            ca_user.write(record)

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
    def __init__(self, dbname, model, mainserver):
        self.mainserver = mainserver
        self.dbname = dbname
        self.isInstalled = True

        try:
            model.env.ref("user_mail.user_mail_sync_view")
            self.isInstalled = True
        except Exception, e:
            self.isInstalled = False
        
        self.passwd_server = get_config('passwd_server','Server uri is missing!')
        self.passwd_dbname = get_config('passwd_dbname','Databasename is missing')
        self.passwd_user   = get_config('passwd_user','Username is missing')
        self.passwd_passwd = get_config('passwd_passwd','Password is missing')

        if not self.mainserver and self.isInstalled:
            try:
                self.sock_common = xmlrpclib.ServerProxy('%s/xmlrpc/common' % self.passwd_server)           
                self.uid = self.sock_common.login(self.passwd_dbname, self.passwd_user, self.passwd_passwd)
                self.sock = xmlrpclib.ServerProxy('%s/xmlrpc/object' % self.passwd_server)
            except xmlrpclib.Error as err:
                raise Warning(_("%s (server %s, db %s, user %s, pw %s)" % (err, self.passwd_server, self.passwd_dbname, self.passwd_user, self.passwd_passwd)))
            
    def search(self,model,domain, mainserver):     
        if not mainserver and self.isInstalled:
            return self.sock.execute(self.passwd_dbname, self.uid, self.passwd_passwd,model, 'search', domain)

    def write(self,model,id,values, mainserver):
        if not mainserver and self.isInstalled:      
            return self.sock.execute(self.passwd_dbname, self.uid, self.passwd_passwd, model, 'write', id, values)

    def create(self,model,values, mainserver):
        if not mainserver and self.isInstalled:
            return self.sock.execute(self.passwd_dbname, self.uid, self.passwd_passwd,model,'create', values)

    def unlink(self,model,ids, mainserver):
        if not mainserver and self.isInstalled:
            return self.sock.execute(self.passwd_dbname, self.uid, self.passwd_passwd, model, 'unlink',ids)

    def remote_company(self, company, mainserver):
        # User company.remote_id for this company
        if not mainserver:
            remote_company = self.search('res.company',[('remote_id','=',company.remote_id)], mainserver)          
            if remote_company:
                return remote_company[0]
            else: 
                return None
    def remote_user(self,user, mainserver):
        # User user.remote_id for this user
        if not mainserver:
            remote_user = self.search('res.user',[('login','=',user.login)], mainserver)
            if remote_user:
                return remote_user[0]
            else: 
                return None


