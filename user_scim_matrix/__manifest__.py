# -*- coding: utf-8 -*-
{
    'name': 'User SCIM — Matrix Extension',
    'version': '18.0.1.0.0',
    'category': 'Tools',
    'summary': 'Sync Matrix ID to LDAP via SCIM bridge',
    'description': """
User SCIM — Matrix Extension
=============================
Lägger till Matrix-ID-fältet på användaren och synkar det till LDAP via
SCIM-bridgen.

Kräver:
- user_scim (SCIM-synk)
- user_matrix (eller motsvarande) — den modul som finns i samma repo

När user_matrix är installerad lägger user_scim_matrix till matrix_id i
SCIM-JSON:en så att det synkas till LDAP-fältet labeledURI.

Tekniskt flöde:
    user_matrix → user_scim_matrix → SCIM hook → LDAP
    """,
    'author': 'Vertel AB',
    'website': 'https://vertel.se',
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
