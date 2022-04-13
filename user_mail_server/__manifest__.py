# -*- coding: utf-8 -*-
##############################################################################
#
#
#
##############################################################################


{
    'name': 'User Mail Server',
    'version': '10.0.0.1',
    'category': 'other',
    'summary': 'Administation of mail for users, serverside component',
    'author': 'Vertel AB',
    'website': 'http://www.vertel.se',
    'depends': ['user_mail_common'],
    'data': ['res_users_view.xml'],

    'installable': True,
    'application': True,
    #'auto_install': False,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
