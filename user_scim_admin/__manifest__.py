# -*- coding: utf-8 -*-
{
    'name': 'User SCIM — Admin Directory',
    'version': '18.0.1.0.0',
    'category': 'Tools',
    'summary': 'Central admin view of all LDAP users across customers.',
    'description': '''
User SCIM — Admin Directory
===========================

    Central view in the management system showing ALL users from ALL customers in
the shared LDAP directory.

Shows data synced via the SCIM bridge from each customer's Odoo instance.

Features:

    - Tree view of all LDAP users with customer affiliation.
    - Filters on customer, active, has Matrix ID, etc.
    - Conflict detection (same uid in several customers).
    ''',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se/apps/odoo-user-mail/user_scim_admin',
    'license': 'AGPL-3',
    'depends': [
        'base',
        'user_scim',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'views/scim_directory_views.xml',
        'views/scim_directory_kanban.xml',
        'views/scim_directory_menus.xml',
        'views/res_config_settings_view.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
