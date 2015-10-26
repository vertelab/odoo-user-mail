# -*- coding: utf-8 -*-
##############################################################################
#
#
#
##############################################################################


{
    'name': 'User mail',
    'version': '1.1',
    'category': 'other',
    'summary': 'Administation of mail for users',
    'author': 'Vertel AB',
    'website': 'http://www.vertel.se',
    'depends': ['base', 'fetchmail'],
    'data': ['res_users_view.xml','security/ir.model.access.csv', 'security/user_mail_security.xml'],

    'installable': True,
    'application': False,
    #'auto_install': False,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
