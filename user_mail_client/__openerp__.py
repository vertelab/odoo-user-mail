# -*- coding: utf-8 -*-
##############################################################################
#
#
#
##############################################################################


{
    'name': 'User mail client',
    'version': '1.2',
    'category': 'other',
    'summary': 'Administation of mail for users on client side',
    'author': 'Vertel AB',
    'website': 'http://www.vertel.se',
    'depends': ['user_password_tmp','fetchmail', 'user_mail_common'],
    'data': ['res_users_view.xml','res_users_data.xml'],

    'installable': True,
    'application': True,
    #'auto_install': False,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
