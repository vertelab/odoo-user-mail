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

def get_config(param,msg):
    import openerp.tools
    value = openerp.tools.config.get(param,False)
    if not value:
        raise Warning(_("%s (%s in /etc/odoo/openerp-server.conf)" % (msg,param)))
    return value


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
        global SYNCSERVER
        if not SYNCSERVER:
            SYNCSERVER = Sync2server(self)

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
            self.env['res.users.password'].update_pw(self.id,record['new_password'])

        record['mail_alias'] = [(0,0,{'mail':m.mail,'active':m.active}) for m in self.mail_alias ]

        remote_user_id = SYNCSERVER.search(self._name,[('login','=',self.login)])

        _logger.warn("REMOTE USER ID FOR USER SYNC IS: %s" % remote_user_id)

        if remote_user_id:
            SYNCSERVER.unlink('postfix.alias',server.search('postfix.alias',[('user_id','=',remote_user_id)]))
            SYNCSERVER.write(self._name,remote_user_id,record)
        else:
            result = SYNCSERVER.create(self._name,record)
            _logger.warn("RESULT: %s" % result)
    
    @api.one
    def write(self,values):
        if values.get('new_password',False):
            self.env['res.users.password'].update_pw(self.id,values.get('new_password'))
            global SYNCSERVER
            if not SYNCSERVER:
                SYNCSERVER = Sync2server(self)
            remote_user_id = SYNCSERVER.search(self._name,[('login','=',self.login)])
            if remote_user_id:
                SYNCSERVER.write(self._name,remote_user_id,{'new_password': values['new_password']})
            else:
                SYNCSERVER.create(self._name,{'new_password': values['new_password']})
        return super(res_users, self).write(values)

    def unlink(self, cr, uid, ids, context=None):
        postfix_alias_ids = self.pool.get('postfix.alias').search(cr, uid, [('user_id', '=', ids)], offset=0, limit=None, order=None, context=None)    
        self.pool.get('postfix.alias').unlink(cr, uid, postfix_alias_ids, context)
        return super(res_users, self).unlink(cr, uid, ids, context)

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
        self.catchall = self.env['ir.config_parameter'].get_param('mail.catchall.alias') or 'catchall' + '@' + self.domain
    catchall = fields.Char(compute=_catchall,string='Catchall',help="catchall mail address",)   
    
    @api.one
    def _total_quota(self):
        self.total_quota = sum([u.quota for u in self.env['res.users'].search([('company_id','=',self.id)])])

    default_quota = fields.Integer('Quota',)
    total_quota = fields.Integer(compute="_total_quota",string='Quota total')    
                
    @api.one
    def write(self,values):
        global SYNCSERVER
        _logger.warn("values in override write is: %s" % values)
        super(res_company, self).write(values)
        #raise Warning(self.sync_settings())
        remote_company_id = self.sync_settings()
        _logger.warn("Domain: %s, base: %r, self: %r" % (values.get('domain'), self.env.ref('base.main_company'), self))
        if values.get('domain',False) and self.id == self.env.ref('base.main_company').id:  # Create mailservers when its a main company

            self.env['ir.config_parameter'].set_param('mail.catchall.domain',values.get('domain'))
            if not SYNCSERVER:
                SYNCSERVER = Sync2server(self)
            if not SYNCSERVER.mainserver():
                password = self._synccatchall(remote_company_id)
                self._smtpserver(password)
                self._imapserver(password) 

            _logger.warn("AFTER IF Base: %s, Self.id: %s" % (self.env.ref('base.main_company'), self.id))           

    @api.model
    def create(self,values):
        id = super(res_company, self).create(values)
        if id:
            remote_company_id = self.sync_settings()
            # does we need this? Will we actually ever create a main_company with a domain set?
            if values.get('domain',False) and id == self.env.ref('base.main_company').id:  # Create mailservers when its a main company
                self.env['ir.config_parameter'].set_param('mail.catchall.domain',values.get('domain'))
                password = self._synccatchall(remote_company_id)
                self._smtpserver(password)
                self._imapserver(password)
        return id

    @api.one
    def sync_settings(self):  
        global SYNCSERVER
        if not SYNCSERVER:
            SYNCSERVER = Sync2server(self)

        record = {f:self.read()[0][f] for f in  ['name','domain','catchall','default_quota', 'email']}

        remote_company_id = SYNCSERVER.search(self._name,[('domain','=',self.domain),])

        _logger.warn("REMOTE ID IS: %s" % remote_company_id)
        _logger.warn("RECORD: %s" % record)

        if remote_company_id:
            #raise Warning('%s %s' % (remote_company_id[0],record))
            SYNCSERVER.write(self._name,remote_company_id[0], record)
        else:
            return SYNCSERVER.create(self._name, record)
        return remote_company_id[0]

    @api.one
    def _synccatchall(self,remote_company_id):
        global SYNCSERVER

        if not SYNCSERVER:
            SYNCSERVER = Sync2server(self)

        record = {
            'new_password': self.env['res.users'].generate_password(),
            'name': 'Catchall', 
            'login': self.catchall, 
            'postfix_active': True, 
            'email': self.catchall, 
            'mail_alias': [(0,0,{'mail': '@%s' % self.domain,'active':True})],
        }

        remote_user_id = SYNCSERVER.search('res.users',[('login','=',self.catchall)])
        #raise Warning('record %s user %s' % (record,remote_user_id))
        if remote_user_id:
            remote_user_id = remote_user_id[0]
            SYNCSERVER.unlink('postfix.alias',SYNCSERVER.search('postfix.alias',[('user_id','=',remote_user_id)]))

            _logger.warn("remote_user_id - _synccatchall : %s" % remote_user_id)

            SYNCSERVER.write('res.users',remote_user_id,record)
 
            record = {'company_id': remote_company_id[0], 'company_ids': [remote_company_id[0]]}
            SYNCSERVER.write('res.users',remote_user_id,record)
        else:
            SYNCSERVER.create('res.users',record)

            record = {'company_id': remote_company_id[0], 'company_ids': [remote_company_id[0]]}
            SYNCSERVER.create('res.users',record)

        _logger.warn("New password = %s" % record['new_password'])

        return record['new_password']  # Return the password for temporary use


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
        smtp = self.env.ref('base.ir_mail_server_localhost0')
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


class Sync2server():
    def __init__(self,model):
        self.dbname = model.env.cr.dbname
        self.passwd_server = get_config('passwd_server','Server uri is missing!')
        self.passwd_dbname = get_config('passwd_dbname','Databasename is missing')
        self.passwd_user   = get_config('passwd_user','Username is missing')
        self.passwd_passwd = get_config('passwd_passwd','Password is missing')

        if not self.mainserver(): # Sender and main server are the same
            try:
                sock_common = xmlrpclib.ServerProxy('%s/xmlrpc/common' % self.passwd_server,verbose=True)              
                self.uid = sock_common.login(self.passwd_dbname, self.passwd_user, self.passwd_passwd)
                self.sock = xmlrpclib.ServerProxy('%s/xmlrpc/object' % self.passwd_server, verbose=True)
            except xmlrpclib.Error as err:
                raise Warning(_("%s (server %s, db %s, user %s, pw %s)" % (err, self.passwd_server,self.passd_dbname,self.passwd_user, self.passwd_passwd)))
            
    def search(self,model,domain):     
        if not self.mainserver():
            return self.sock.execute(self.passwd_dbname, self.uid,self.passwd_passwd,model, 'search', domain)
    def write(self,model,id,values):
        if not self.mainserver():
            #raise Warning('%s %s %s' % (model,id,values))
            _logger.warn("VALS: %s remote-id: %s" % (values,id))            
            return self.sock.execute(self.passwd_dbname, self.uid,self.passwd_passwd, model, 'write',id, values)
    def create(self,model,values): 
        if not self.mainserver():
            _logger.warn("VALS: %s" % values)

            return self.sock.execute(self.passwd_dbname, self.uid,self.passwd_passwd,model,'create', values)
    def unlink(self,model,ids):
        if not self.mainserver():
            return self.sock.execute(self.passwd_dbname, self.uid,self.passwd_passwd,model,'unlink',ids)

    def mainserver(self):
        return self.dbname == self.passwd_dbname # If local/remote database has the same name we asume its the same database / the mainserver
        #~ from urlparse import urlparse       
        #~ import socket
#~ 
        #~ host = urlparse(self.passwd_server)
        #~ hostname = host.hostname
#~ 
        #~ hostname = self.passwd_server.split("://")[1] #Do this to get rid of "http://" in the hostname from config file (which is needed for the XML-RPC-request)
        #~ if socket.gethostbyname(hostname) == socket.gethostbyname(socket.gethostname()) and self.env.cr.dbname == self.passwd_dbname:
            #~ return True
        #~ else:
            #~ return False
