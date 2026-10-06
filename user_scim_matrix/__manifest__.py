# -*- coding: utf-8 -*-
{
    'name': 'User SCIM — Matrix Extension',
    'version': '18.0.1.0.0',
    'category': 'Tools',
    'summary': 'Sync Matrix ID to LDAP via SCIM bridge.',
    'description': '''
User SCIM — Matrix Extension
============================

    Adds the Matrix ID field to the user and syncs it to LDAP via the SCIM bridge.

Requires:

    - user_scim (SCIM sync)
    - user_matrix (or equivalent)

When user_matrix is installed, user_scim_matrix adds matrix_id to the SCIM
JSON so that it is synced to the LDAP field labeledURI.
    ''',
    'author': 'Vertel AB',
    'website': 'https://vertel.se/apps/odoo-user-mail/user_scim_matrix',
    'license': 'AGPL-3',
    'depends': [
        'user_scim',
        'user_matrix',  # när den är klar, byt till faktiskt modulnamn
    ],
    'data': [
        'views/res_users_view.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
