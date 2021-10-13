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

from odoo import models, fields, api, _
from odoo.exceptions import Warning
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class postfix_alias_copy(models.Model):
    _name = "postfix.alias.copy"
    _description = "Postfix Alias Copy"

    user_id_copy = fields.Many2one('res.users')
    mail_copy = fields.Char('Mail Copy')
    active_copy = fields.Boolean('Active Copy')


class res_users(models.Model):
    _inherit = "res.users"

    postfix_active_copy = fields.Boolean('Active Copy')
    vacation_subject_copy = fields.Char('Subject Copy')
    vacation_text_copy =  fields.Text('Text Copy')
    vacation_active_copy =  fields.Boolean('Active Copy')
    vacation_from_copy = fields.Date('From Copy')
    vacation_to_copy = fields.Date('To Copy')
    vacation_forward_copy = fields.Char('Forward Copy')
    forward_active_copy = fields.Boolean('Active Copy')
    forward_address_copy = fields.Text('Forward address Copy')
    forward_cp_copy = fields.Boolean('Keep Copy')
    virus_active_copy = fields.Boolean('Virus Check Copy')
    spam_active_copy = fields.Boolean('Spam Check Copy')
    spam_killevel_copy = fields.Selection([('10', 'low (10)'), ('6', 'medium (6)'), ('4.5', 'high (4.5)'), ('3', 'very high (3)')]  ,string='Spam Kill Level Copy')
    spam_tag2_copy = fields.Selection([('9.5', 'low (9.5)'), ('5.5', 'medium (5.5)'), ('4', 'high (4)'), ('2.5', 'very high (2.5)')], string='Spam Tag Level two Copy')
    spam_tag_copy = fields.Selection([('7.0', 'low (7)'), ('3', 'medium (3)'),('1.5', 'high (1.5)'),('0', 'very high (0)')], string='Spam Tag Level Copy')
    maildir_copy = fields.Char('Maildir Copy')
    transport_copy = fields.Char('Transport Copy')
    domain_copy  = fields.Char('Domain Copy')
    mail_alias_copy = fields.One2many('postfix.alias.copy', 'user_id_copy', string='Alias Copy')
    dovecot_password_copy = fields.Char('Dovecot Password Copy')

    def _copy_res_users(self, cr, uid, ids, context=None):
        users = self.pool.get('res.users').browse(cr, uid, ids, context=context)
        
        for user in users:
            user.write({'postfix_active_copy': user.postfix_active,
                        'vacation_subject_copy': user.vacation_subject,
                        'vacation_text_copy': user.vacation_text,
                        'vacation_active_copy': user.vacation_active,
                        'vacation_from_copy': user.vacation_from,
                        'vacation_to_copy': user.vacation_to,
                        'vacation_forward_copy': user.vacation_forward,
                        'forward_active_copy': user.forward_active,
                        'forward_address_copy': user.forward_address,
                        'forward_cp_copy': user.forward_cp,
                        'virus_active_copy': user.virus_active,
                        'spam_active_copy': user.spam_active,
                        'spam_killevel_copy': user.spam_killevel,
                        'spam_tag2_copy': user.spam_tag2,
                        'spam_tag_copy': user.spam_tag,
                        'maildir_copy': user.maildir,
                        'transport_copy': user.transport,
                        'domain_copy': user.domain,                        
                        'dovecot_password_copy': user.dovecot_password,
                        'mail_alias_copy': [(0, _, {'mail_copy': m.mail, 'active_copy': m.active}) for m in user.mail_alias]
                        })


    def _set_res_users(self, cr, uid, ids, context=None):
        users = self.browse(cr, uid, ids, context)
        for user in users:
            user.write({'postfix_active': user.postfix_active_copy,
                        'vacation_subject': user.vacation_subject_copy,
                        'vacation_text': user.vacation_text_copy,
                        'vacation_active': user.vacation_active_copy,
                        'vacation_from': user.vacation_from_copy,
                        'vacation_to': user.vacation_to_copy,
                        'vacation_forward': user.vacation_forward_copy,
                        'forward_active': user.forward_active_copy,
                        'forward_address': user.forward_address_copy,
                        'forward_cp': user.forward_cp_copy,
                        'virus_active': user.virus_active_copy,
                        'spam_active': user.spam_active_copy,
                        'spam_killevel': user.spam_killevel_copy,
                        'spam_tag2': user.spam_tag2_copy,
                        'spam_tag': user.spam_tag_copy,
                        'maildir': user.maildir_copy,
                        'transport': user.transport_copy,
                        'domain': user.domain_copy,
                        'dovecot_password': user.dovecot_password_copy,
                        'mail_alias': [(0, _, {'mail': m.mail_copy, 'active': m.active_copy}) for m in user.mail_alias_copy]
                        })


    def _set_all_models(self, cr, uid, ids, context=None):
        user_ids = self.pool.get('res.users').search(cr, uid, [], context=context)
        company_ids = self.pool.get('res.company').search(cr, uid, [], context=context)

        self.pool.get('res.users')._set_res_users(cr, uid, user_ids, context)
        self.pool.get('res.company')._set_res_company(cr, uid, company_ids, context)


    @api.model
    def add_to_more_button(self):
        record = self.env.ref("user_info_copy.copy_action")
        record.create_action()

class res_company(models.Model):
    _inherit = 'res.company'

    default_quota_copy = fields.Integer('Quota Copy')
    total_quota_copy = fields.Integer('Quota total Copy')   
    remote_id_copy = fields.Char('Remote ID Copy')
    domain_copy = fields.Char('Domain Copy')
    catchall_copy = fields.Char('Catchall Copy') 

    def _copy_res_company(self, cr, uid, ids, context=None):
        companies = self.browse(cr, uid, ids, context)
        for company in companies:
            company.write({'default_quota_copy': company.default_quota,
                           'total_quota_copy': company.total_quota,
                           'remote_id_copy': company.remote_id,
                           'domain_copy': company.domain,
                           'catchall_copy': company.catchall})

    def _set_res_company(self, cr, uid, ids, context=None):
        companies = self.browse(cr, uid, ids, context)
        for company in companies:
            company.write({'default_quota': company.default_quota_copy,
                           'total_quota': company.total_quota_copy,
                           'remote_id': company.remote_id_copy,
                           'domain': company.domain_copy,
                           'catchall': company.catchall_copy})


class module(models.Model):
    _inherit = "ir.module.module"   

    def module_uninstall(self, cr, uid, ids, context=None):
        user_ids = self.pool.get('res.users').search(cr, uid, [], context=context)
        company_ids = self.pool.get('res.company').search(cr, uid, [], context=context)

        self.pool.get('res.users')._copy_res_users(cr, uid, user_ids, context)
        self.pool.get('res.company')._copy_res_company(cr, uid, company_ids, context)

        return super(module, self).module_uninstall(cr, uid, ids, context)
