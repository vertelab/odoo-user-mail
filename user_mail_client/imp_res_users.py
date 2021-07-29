# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015 - 2019 Vertel AB (<http://www.vertel.se>).
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

from odoo import models, fields, api, _
import odoo.tools
from odoo.tools import safe_eval as eval

try:
    from xmlrpc import client as xmlrpclib
except ImportError:
    import xmlrpclib
import xmlrpc.client
from odoo.exceptions import Warning
import os, string
import random
import logging

_logger = logging.getLogger(__name__)
import uuid
from passlib.hash import sha512_crypt

SYNCSERVER = None


def get_config(param, msg):
    value = odoo.tools.config.get(param, False)
    if not value:
        raise Warning(_("%s (%s in /etc/odoo/odoo.conf)" % (msg, param)))
    return value


class sync_settings_wizard(models.TransientModel):
    _name = "user.mail.sync.wizard"
    _description = "User Mail Sync Wizard"

    gen_pw = fields.Boolean(string="generate_password")

    def default_user_ids(self):
        return self.env['res.users'].sudo().browse(self._context.get('active_ids'))

    def sync_settings(self):
        companies = set()
        nopw = list()
        for user in self.default_user_ids():
            if not self.gen_pw and not user.dovecot_password and user.passwd_tmp == _('N/A'):
                nopw.append(user)
            self.env['res.users'].user_sync_settings(user)
            if self.gen_pw:
                user.write({'new_password': user.generate_password()})
            companies.add(user.company_id)
        for c in companies:
            self.env['res.company'].company_sync_settings(c)

        if len(nopw) > 0:
            raise Warning(_('Some users missing password:\n\n%s\n\n please set new (sync is done)') % ',\n'.join(
                [u.login for u in nopw]))

        return {}


class res_users(models.Model):
    _inherit = 'res.users'

    def _get_param(self, param, value):
        if not self.env['ir.config_parameter'].get_param(param):
            self.env['ir.config_parameter'].set_param(param, value)
        return self.env['ir.config_parameter'].get_param(param)

    def generate_password(self):
        length = int(self._get_param('pw_length', 13))
        rules = eval(self._get_param('pw_rules', str({
            'lower': 4,
            'upper': 3,
            'digits': 2,
            'special': 1,
        })))
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
        return sha512_crypt.encrypt(pw)

    def generateUUID(self):
        return str(uuid.uuid4())

    def remote_user(self, user):
        remote_user = None
        if not user.remote_id and user.postfix_mail:
            remote_user = self.env['res.users'].search([('postfix_mail', '=', user.postfix_mail), ('login', '=', user.login)])
            _logger.info(':::::::::1%s', remote_user)
        elif not user.remote_id:
            remote_user = self.env['res.users'].search([('login', '=', user.login)])
            _logger.info(':::::::::2%s', remote_user)
        if not user.remote_id:
            user.remote_id = str(uuid.uuid4())
            if remote_user:
                remote_user.write({'remote_id': user.remote_id})
            _logger.info(':::::::::3%s', remote_user)
        if user.remote_id:
            remote_user = self.env['res.users'].search([('remote_id', '=', user.remote_id)])
            _logger.info(':::::::::4%s', remote_user)
        _logger.info(':::::::::5555%s', remote_user)
        return remote_user

    def user_sync_settings(self, user):
        record = {f: user.read()[0][f] for f in user.USER_MAIL_FIELDS}
        record['postfix_alias_ids'] = [(0, 0, {'name': m.name, 'mail': m.mail, 'active': m.active}) for m in
                                       self.postfix_alias_ids]

        remote_company = self.env['res.company'].remote_company(user.company_id)
        if remote_company:
            record['company_ids'] = [(6, _, [remote_company.id])]
            record['company_id'] = remote_company.id
        else:
            raise Warning('Update company first')

        remote_user_id = self.remote_user(user)
        _logger.info('userrr-%s', user)
        _logger.info('remote_user_id-%s', remote_user_id)
        if remote_user_id:
            _logger.info('-------%s', remote_user_id)
            postfix_alias_id = self.env['postfix.alias'].search([('user_id', '=', remote_user_id.id)], limit=1)
            postfix_alias_id.unlink()
            remote_user_id.write(record)
        else:
            record['remote_id'] = self.remote_id
            self.env['res.users'].create(record)

    def write(self, values):
        passwd = values.get('password') or values.get('new_password')
        if passwd:
            values['dovecot_password'] = self.generate_dovecot_sha512(passwd)
            remote_user_id = self.remote_user(self)
            if remote_user_id:
                _logger.info("VALUES IN WRITE :::::::::: %s" % values)
                remote_user_id.write(values)
        return super(res_users, self).write(values)

    def unlink(self):
        user_id = self.env['res.users'].sudo().search([('login', '=', self.login)]).id
        self.env['postfix.alias'].search([('user_id', '=', user_id)]).unlink()
        # only needed if deleting a user with recently changed password
        self.env['change.password.wizard'].search([('user_ids', '=', self.id)]).unlink()
        self.env['change.password.user'].search([('user_id', '=', self.id)]).unlink()

        remote_user = self.remote_user(self)
        if remote_user:
            remote_user.unlink()

        return super(res_users, self).unlink()

    # def testxmlrpc(self):
    #     # ~ common = xmlrpc.client.ServerProxy('http://localhost:8069/xmlrpc/2/common')
    #     # ~ info = common.version()
    #     # ~ uid = common.authenticate('mail_server', 'admin', 'admin', {})
    #     # ~ model = xmlrpc.client.ServerProxy('http://localhost:8069/xmlrpc/2/object',allow_none=True)
    #
    #     # ~ res = model.execute_kw('mail_server', uid, 'admin','res.company', 'search', [[['remote_id','=',None]]])
    #     # ~ raise Warning(res,info,uid)
    #     # ~ #_logger.error(res)
    #
    #     SYNCSERVER = Sync2server(self)
    #     # ~ record = {f:self.read()[0][f] for f in self.USER_MAIL_FIELDS}
    #     # ~ record['postfix_alias_ids'] = [(0,0,{'name': m.name, 'mail':m.mail,'active':m.active}) for m in self.postfix_alias_ids]
    #
    #     # ~ res = SYNCSERVER.sock.execute_kw(SYNCSERVER.passwd_dbnameSYNCSERVER.passwd_dbname, SYNCSERVER.uid, SYNCSERVER.passwd_passwd,'res.users', 'search', [[['id','=',1]]])
    #     res = SYNCSERVER.sock.execute_kw('mail_server', 1, 'admin', 'res.users', 'search', [['id', '=', 1]])
    #     _logger.error(res)
    #
    #     remote_company = SYNCSERVER.search('res.company', [['remote_id', '=', None]])
    #
    #     remote_company = SYNCSERVER.remote_company(self.company_id)
    #
    #     # raise Warning(uid,info)


class res_company(models.Model):
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
        comp = super(res_company, self).write(values)
        if values.get('domain', False):
            _logger.info('::::::::::values', values)
            self.company_sync_settings()

            if self.id == self.env.ref(
                    'base.main_company').id:  # Create mailservers when its a main company and not mainserver
                self.env['ir.config_parameter'].set_param('mail.catchall.domain', values.get('domain'))
                password = self._createcatchall()[0]
                if password:
                    self._smtpserver(password)
                    self._imapserver(password)
        return comp

    def unlink(self):
        remote_company = self.remote_company(self)
        if remote_company:
            remote_company.unlink()
        super(res_company, self).unlink()

    @api.model
    def create(self, values):
        values['remote_id'] = self.generateUUID()
        company = super(res_company, self).create(values)

        if company:
            remote_company_id = company.company_sync_settings()

            if values.get('domain', False) and self.id == self.env.ref('base.main_company').id:  # Create mailservers when its a main company and not mainserver
                self.env['ir.config_parameter'].set_param('mail.catchall.domain', values.get('domain'))
                password = company._createcatchall()[0]
                self._smtpserver(password)
                self._imapserver(password)

        return company

    def company_sync_settings(self, comp_id):
        record = {f: comp_id.read()[0][f] for f in ['name', 'domain', 'catchall', 'default_quota', 'email', 'remote_id']}
        remote_company_id = False
        if self.remote_id:
            remote_company_id = self.remote_company(comp_id)

        _logger.info(':::::::::::%s, ---- %s, +++++++', (self.remote_id, remote_company_id))
        if self.remote_id and remote_company_id:
            _logger.info(':::::::::::%s, ---- %s, +++++++ %s', (self._name, remote_company_id, record))
            remote_company_id.write(record)
            return remote_company_id
        else:
            return self.env['res.company'].create(record)

    def _createcatchall(self):
        if not self.env['res.user'].search([('postfix_mail', '=', self.catchall)]):
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

            remote_company = self.remote_company(self)

            if remote_company:
                record['company_ids'] = [(6, _, [remote_company])]
                record['company_id'] = remote_company

            self.env['res.users'].create(record)
            return new_pw

    def remote_company(self, company):
        if not company.remote_id:
            raise Warning('no remote id')
        remote_company = self.env['res.company'].search([('remote_id', '=', company.remote_id)])
        if remote_company:
            return remote_company
        else:
            remote_company = self.env['res.company'].search([('domain', '=', company.domain)])
            _logger.info('%s::::::remote company----%s', (company.domain, remote_company))
            # if len(remote_company) == 0:
            #     return self.env['res.company'].create({'name': company.name, 'domain': company.domain,
            #                                            'remote_id': company.remote_id})
            # else:
            #     remote_company.write({'remote_id': company.remote_id})
            #     return remote_company

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
            pass

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
            'type': 'imap',
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
                _logger.warning("Company %s new remote id (%s)" % (company.name, company.domain))
                company.write({'domain': company.domain})
