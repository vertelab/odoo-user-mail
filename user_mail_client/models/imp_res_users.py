# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015 - 2019 Vertel AB (<http://www.vertel.se>).
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
from passlib.hash import sha512_crypt
import random
import string
import uuid
try:
    from xmlrpc import client as xmlrpclib
except ImportError:
    import xmlrpclib
import xmlrpc.client

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import odoo.tools

_logger = logging.getLogger(__name__)


def get_config(param, msg):
    value = odoo.tools.config.get(param, False)
    if not value:
        raise UserError(_("%s (%s in /etc/odoo/odoo.conf)" % (msg, param)))
    return value


class SyncSettingsWizard(models.TransientModel):
    _name = "user.mail.sync.wizard"
    _description = "User Mail Sync Wizard"

    gen_pw = fields.Boolean(string="generate_password")

    def _default_user_ids(self):
        return self.env['res.users'].sudo().browse(self._context.get('active_ids'))

    def sync_settings(self):
        companies = set()
        nopw = list()
        for user in self._default_user_ids():
            if not self.gen_pw and not user.dovecot_password and user.passwd_tmp == _('N/A'):
                nopw.append(user)
            user.user_sync_settings()
            if self.gen_pw:
                user.write({'new_password': user.generate_password()})
            companies.add(user.company_id)
        for c in companies:
            c.company_sync_settings()

        if len(nopw) > 0:
            raise UserError(_('Some users missing password:\n\n%s\n\n please set new (sync is done)') % ',\n'.join(
                [u.login for u in nopw]))

        return {}


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _get_param(self, param, value):
        if not self.env['ir.config_parameter'].get_param(param):
            self.env['ir.config_parameter'].set_param(param, value)
        return self.env['ir.config_parameter'].get_param(param)

    def generate_password(self):
        length = int(self._get_param('pw_length', 13))
        rules = {
            'lower': 4,
            'upper': 3,
            'digits': 2,
            'special': 1,
        }
        char_types = list(rules.keys())
        chars = {
            'lower': string.ascii_lowercase,
            'upper': string.ascii_uppercase,
            'digits': string.digits,
            'special': '+_-!@#$%&*()',
        }
        password = []
        for char_type in char_types:
            for i in range(rules[char_type]):
                password.append(random.choice(chars[char_type]))
        while len(password) < length:
            char_type = random.choice(char_types)
            password.append(random.choice(chars[char_type]))
        random.shuffle(password)
        return ''.join(password)

    def generate_dovecot_sha512(self, pw):
        return sha512_crypt.hash(pw)

    def generateUUID(self):
        return str(uuid.uuid4())

    def user_sync_settings(self):
        syncserver = Sync2server()
        for record in self:
            # Should allways be just one result in this list.
            sync_record = record.read(self.USER_MAIL_FIELDS)[0]
            aliases = [(0, 0,
                        {'name': m.name, 'mail': m.mail, 'active': m.active})
                       for m in record.postfix_alias_ids]
            sync_record['postfix_alias_ids'] = aliases
            remote_company = syncserver.remote_company(record.company_id)
            if remote_company:
                sync_record['company_ids'] = [(6, _, [remote_company])]
                sync_record['company_id'] = remote_company
            else:
                raise UserError(_('Update company first'))
            remote_user_id = syncserver.remote_user(record)
            if remote_user_id:
                # Check postfix_alias_ids
                syncserver.unlink('postfix.alias', syncserver.search(
                    'postfix.alias', [['user_id', '=', remote_user_id]]))
                syncserver.write(self._name, remote_user_id, sync_record)
            else:
                sync_record['remote_id'] = self.remote_id
                syncserver.create(self._name, sync_record)

    def write(self, values):
        passwd = values.get('password') or values.get('new_password')
        if passwd:
            values['dovecot_password'] = self.generate_dovecot_sha512(passwd)
            syncserver = Sync2server()
            remote_user_id = syncserver.remote_user(self)
            if remote_user_id:
                _logger.info(f"VALUES IN WRITE :::::::::: {values}")
                syncserver.write(self._name, remote_user_id, values)

            if remote_user_id == self.env.user and values.get('new_password'):
                password_wizard = self.env['change.password.wizard'].create({
                    'user_ids': [(0, 0, {
                        'user_id': remote_user_id.id,
                        'user_login': remote_user_id.login,
                        'new_passwd': values.get('new_password')
                    })]
                })
                password_wizard.change_password_button()
                del values['new_password']
                _logger.info(f"VALUES IN WRITE :::::::::: {values}")
        return super(ResUsers, self).write(values)

    def unlink(self):
        syncserver = Sync2server()

        user_id = self.env['res.users'].search([('login', '=', self.login)]).id
        self.env['postfix.alias'].search([('user_id', '=', user_id)]).unlink()
        # only needed if deleting a user with recently changed password
        self.env['change.password.wizard'].search([('user_ids', '=', self.id)]).unlink()
        self.env['change.password.user'].search([('user_id', '=', self.id)]).unlink()

        remote_user = syncserver.remote_user(self)
        if remote_user:
            syncserver.unlink(self._name, [remote_user])

        return super(ResUsers, self).unlink()


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _get_param(self, param, value):
        if not self.env['ir.config_parameter'].get_param(param):
            self.env['ir.config_parameter'].set_param(param, value)
        return self.env['ir.config_parameter'].get_param(param)

    def generateUUID(self):
        return str(uuid.uuid4())

    def write(self, values):
        if not self.remote_id:
            values['remote_id'] = self.generateUUID()
        super(ResCompany, self).write(values)
        domain = values.get('domain')
        if domain:
            self.company_sync_settings()
            # Create mail servers when its a main company
            if self.id == self.env.ref('base.main_company').id:
                self.env['ir.config_parameter'].set_param(
                    'mail.catchall.domain', domain)
                password = self._createcatchall()
                if password:
                    self._smtpserver(password[0])
                    self._imapserver(password[0])

    def unlink(self):
        syncserver = Sync2server()
        for rec in self:
            remote_company = syncserver.remote_company(rec)
            if remote_company:
                syncserver.unlink(rec._name, remote_company)
        super(ResCompany, self).unlink()

    @api.model
    def create(self, values):
        values['remote_id'] = self.generateUUID()
        company = super(ResCompany, self).create(values)

        if company:
            company.company_sync_settings()
            domain = values.get('domain')
            # Create mailservers when its a main company and not mainserver
            if domain and self.id == self.env.ref('base.main_company').id:
                self.env['ir.config_parameter'].set_param(
                    'mail.catchall.domain', domain)
                password = company._createcatchall()[0]
                self._smtpserver(password)
                self._imapserver(password)
        return company

    def company_sync_settings(self):
        syncserver = Sync2server()
        fields = ['name', 'domain', 'catchall', 'default_quota', 'email', 'remote_id']
        for record in self:
            # Should always be one dictionary here.
            sync_record = record.read(fields)[0]
            remote_company_id = False
            if record.remote_id:
                remote_company_id = syncserver.remote_company(record)

            if record.remote_id and remote_company_id:
                syncserver.write(self._name, remote_company_id, sync_record)
                return remote_company_id
            else:
                return syncserver.create(self._name, sync_record)

    def _createcatchall(self):
        syncserver = Sync2server()
        if not syncserver.search('res.users', [['postfix_mail', '=', self.catchall]]):
            new_pw = self.env['res.users'].sudo().generate_password()

            record = {
                'new_password': new_pw,
                'name': 'Catchall',
                'login': self.catchall,
                'postfix_active': True,
                'email': self.catchall,
                'postfix_mail': self.catchall,
                'postfix_alias_ids': [(0, 0, {'name': '', 'active': True})],
                'dovecot_password': self.env['res.users'].sudo().generate_dovecot_sha512(new_pw)
            }

            remote_company = syncserver.remote_company(self)

            if remote_company:
                record['company_ids'] = [(6, _, [remote_company])]
                record['company_id'] = remote_company

                syncserver.create('res.users', record)
                return new_pw

    def _smtpserver(self, password):
        record = {
            'name': 'smtp',
            'smtp_host': get_config('smtp_server', 'SMTP-server missing!'),
            'smtp_port': get_config('smtp_port', 'SMTP-port missing!'),
            'smtp_encryption': get_config('smtp_encryption', 'SMTP-encryption missing!'),
            'smtp_user': self.catchall,
            'smtp_pass': password,
            'sequence': 10,
        }

        smtp = None

        try:
            smtp = self.env.ref('base.ir_mail_server_localhost0')
        except Exception as e:
            _logger.warning(f"error::: {e}")

        if smtp:
            smtp.write(record)
        else:
            self.env['ir.mail_server'].create(record)

    def _imapserver(self, passwd):
        record = {
            'name': 'imap',
            'server': get_config('imap_host', 'IMAP name missing!'),
            'port': get_config('imap_port', 'IMAP port missing!'),
            'is_ssl': True,
            'server_type': 'imap',
            'active': True,
            'state': 'done',
            'user': self.catchall,
            'password': passwd,
        }
        imap = self.env['fetchmail.server'].search([], order='priority desc', limit=1)
        if not imap:
            self.env['fetchmail.server'].create(record)
        else:
            imap.write(record)

    def _set_remote_id(self):
        for company in self.env['res.company'].search([]):
            if not company.remote_id and company.domain:
                _logger.warning(f"Company {company.name} new remote id {company.domain}")
                company.write({'domain': company.domain})


class Sync2server():
    def __init__(self):
        self.passwd_server = get_config('passwd_server', 'Server uri is missing!')
        self.passwd_port = get_config('passwd_port', 'Server port is missing!')
        self.passwd_dbname = get_config('passwd_dbname', 'Database name is missing')
        self.passwd_user = get_config('passwd_user', 'Username is missing')
        self.passwd_passwd = get_config('passwd_passwd', 'Password is missing')
        _logger.info(f"Sync2server server {self.passwd_server} database {self.passwd_dbname} user {self.passwd_user}")
        try:
            self.sock_common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % self.passwd_server)
            self.uid = self.sock_common.authenticate(self.passwd_dbname, self.passwd_user, self.passwd_passwd, {})
            self.sock = xmlrpc.client.ServerProxy('%s/xmlrpc/2/object' % self.passwd_server)
            _logger.info(f"self.sock {self.sock}")
        except xmlrpclib.Fault as err:
            raise UserError(_("%s (server %s, db %s, user %s, pw %s)" % (err, self.passwd_server, self.passwd_dbname,
                                                                       self.passwd_user, self.passwd_passwd)))

    def search(self, model, domain):
        _logger.info(f"search.sock {self.sock}")
        return self.sock.execute_kw(self.passwd_dbname, self.uid, self.passwd_passwd, model, 'search', [domain])

    def write(self, model, rec_id, values):
        _logger.warning(f"model: {model} \n rec_id: {rec_id} \n values: {values}")
        return self.sock.execute_kw(self.passwd_dbname, self.uid, self.passwd_passwd, model, 'write',
                                    [[rec_id], values])

    def create(self, model, values):
        _logger.warning(f"model: {model} \n values: {values}")
        return self.sock.execute_kw(self.passwd_dbname, self.uid, self.passwd_passwd, model, 'create', [values])

    def unlink(self, model, ids):
        return self.sock.execute_kw(self.passwd_dbname, self.uid, self.passwd_passwd, model, 'unlink', [ids])

    def remote_company(self, company):
        if not company.remote_id:
            raise UserError(_('no remote id'))
        remote_company = self.search('res.company', [['remote_id', '=', company.remote_id]])
        if remote_company:
            return remote_company[0]
        else:
            remote_company = self.search('res.company', [['domain', '=', company.domain]])
            if len(remote_company) == 0:
                if not company.domain:
                    raise UserError(_("No domain set for the user's company"))
                return self.create(
                    'res.company',
                    {'name': company.name, 'domain': company.domain, 'remote_id': company.remote_id})
            else:
                self.write('res.company', remote_company[0], {'remote_id': company.remote_id})
                return remote_company[0]

    def remote_user(self, user):
        remote_user = None
        if not user.remote_id and user.postfix_mail:
            remote_user = self.search('res.users',
                                      ['|', ['postfix_mail', '=', user.postfix_mail], ['login', '=', user.login]])
        elif not user.remote_id:
            remote_user = self.search('res.users', [['login', '=', user.login]])
        if not user.remote_id:
            user.remote_id = str(uuid.uuid4())
            if remote_user:
                self.write('res.users', remote_user[0], {'remote_id': user.remote_id})
        remote_user = self.search('res.users', [['remote_id', '=', user.remote_id]])
        return remote_user and remote_user[0] or False
