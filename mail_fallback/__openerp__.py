# -*- coding: utf-8 -*-
##############################################################################
#
#
#
##############################################################################


{
    'name': 'Mail Fallback',
    'version': '1.0',
    'category': 'Tools',
    'summary': 'Catch mail that Odoo does not sort',
    'author': 'Vertel AB',
    'website': 'http://www.vertel.se',
    'depends': ['mail'],
    'data': ['mail_fallback_view.xml'], # 'res_users_view.xml',],
    'installable': True,
    'application': False,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
