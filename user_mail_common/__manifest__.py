# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo SA, Open Source Management Solution, third party addon
#    Copyright (C) 2023- Vertel Sverige AB (<https://vertel.se>).
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
    'name': 'User Mail: User Mail Common',
    'version': '18.0.1.1.0',
    # Version ledger: 14.0 = Odoo version. 1 = Major. Non regressionable code. 2 = Minor. New features that are regressionable. 3 = Bug fixes
    'summary': 'Administration of mail for users on client side.',
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/14.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Technical',
    'description': '''
User Mail Common
================

    Administration of mail for users on client side.

    Features:

        - UI Integration: Extends 1 view(s) in the Odoo interface.
        - Extends Odoo: Builds on postfix.alias, postfix.vacation_notification.
    ''',
    #'sequence': '1',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se/apps/odoo-user-mail/user_mail_common',
    'images': ['static/description/banner.png'], # 560x280 px.
    'license': 'AGPL-3',
    'contributor': '',
    'maintainer': 'Vertel Sverige AB',
    'repository': 'https://github.com/vertelab/odoo-user-mail',
    # Any module necessary for this one to work correctly

    # `mail` krävs: menyn hänger under mail.menu_root_discuss och
    # mail.menu_configuration. Utan beroendet laddas den här modulen före
    # mail och menyn får ingen förälder — Odoo 18 kastar då
    # "External ID not found" vid uppgradering på en ren installation.
    # Det syntes aldrig här eftersom mail alltid redan var installerad.
    'depends': ['base', 'base_setup', 'mail'],
    'external_dependencies': {
        # sievelib: ManageSieve-klient (RFC 5804) + Sieve-parser/factory.
        # KRITISK — utan den kan inga server-side regler eller vacation
        # skickas. Finns i requirements.txt (repo_apply verifierar).
        'python': ['sievelib'],
    },
    'data': [
        'security/user_mail_security.xml',
        'security/ir.model.access.csv',
        'security/sieve_rules.xml',
        'data/cron_sieve_vacation.xml',
        'views/res_users_view.xml',
        'views/sieve_script_views.xml',
        'views/menus_views.xml'
    ],
    'installable': True,
    'application': False,
}
