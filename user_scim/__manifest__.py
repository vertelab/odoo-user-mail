# -*- coding: utf-8 -*-
{
    'name': 'User SCIM Sync',
    'version': '18.0.1.0.0',
    'category': 'Tools',
    'summary': 'Sync users to central LDAP via SCIM 2.0 bridge.',
    'description': '''
User SCIM Sync
==============

    Pushes user changes (create/update/delete) to a SCIM 2.0 bridge that writes
to a shared OpenLDAP directory.

Core module for syncing Vertel users from an Odoo (customer portal) to the
central LDAP directory. Used by all customers.

Fields synced:

    - name, login, email
    - postfix_active, postfix_mail
    - forward_active, forward_address
    - quota, spam_kill_level
    ''',
    'author': 'Vertel AB',
    'website': 'https://vertel.se/apps/odoo-user-mail/user_scim',
    'license': 'AGPL-3',
    'depends': [
        'base',
        'user_mail_common',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_users_view.xml',
        'views/res_config_settings_view.xml',
        'data/cron.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
