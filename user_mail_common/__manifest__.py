# -*- coding: utf-8 -*-
{
    'name': 'User Mail Common',
    'version': '14.0.1.0.0',
    'category': 'other',
    'summary': 'Administation of mail for users',
    'author': 'Vertel AB',
    'website': 'https://www.vertel.se',
    'depends': ['base', 'base_setup'],
    'data': ['security/user_mail_security.xml', 'security/ir.model.access.csv', 'res_users_view.xml'],
    'installable': True,
    'application': False,
}
