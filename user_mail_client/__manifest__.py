# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo SA, Open Source Management Solution, third party addon
#    Copyright (C) 2023- Vertel AB (<https://vertel.se>).
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
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    'name': 'User Mail: User Mail Client',
    'version': '14.0.1.0.1',
    # Version ledger: 14.0 = Odoo version. 1 = Major. Non regressionable code. 2 = Minor. New features that are regressionable. 3 = Bug fixes
    'summary': 'Administration of mail for users on client side.',
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/14.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Technical',
    'description': """
    Client side configuration of mail accounts
    use this in /etc/odoo/openerp-server.conf:
    # mail_server
    passwd_server = localhost
    passwd_dbname = mail_server
    passwd_user = admin
    passwd_passwd = admin
    # for smtp-configuration
    smtp_host = localhost
    smtp_port = 8069
    smtp_encryption = yes
    smtp_user = admin
    smtp_pass = admin
    # for imap-configuration
    imap_host = localhost
    imap_port = 8069
    """,
    #'sequence': '1',
    'author': 'Vertel AB',
    'website': 'https://vertel.se/apps/odoo-user-mail/user_mail_client',
    'images': ['static/description/banner.png'], # 560x280 px.
    'license': 'AGPL-3',
    'contributor': '',
    'maintainer': 'Vertel AB',
    'repository': 'https://github.com/vertelab/odoo-user-mail',
    # Any module necessary for this one to work correctly

    'depends': ['user_password_tmp', 'fetchmail', 'user_mail_common'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_users_view.xml',
        'views/res_users_data.xml',
        'views/res_users_report.xml'
    ],
    'installable': True,
    'application': True,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
