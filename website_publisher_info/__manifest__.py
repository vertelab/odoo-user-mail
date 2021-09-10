# -*- coding: utf-8 -*-
##############################################################################
#
#
#
##############################################################################


{
    'name': 'Website Publisher Info',
    'version': '14.0.1.0.0',
    'category': 'other',
    'summary': 'Information about the website for a website publisher',
    'author': 'Vertel AB',
    'website': 'http://www.vertel.se',
    'depends': ['base', 'user_password_tmp'],
    'data': ['website_publisher_info.xml',],
    'description': ''' 
    This module adds a webpage (/website/publisher_info) with information about the responsible person is for this website. 
    This moduele is maintained from: https://github.com/vertelab/odoo-user-mail/tree/14.0/website_publisher_info 
    ''',
    'installable': True,
    'application': False,
    #'auto_install': False,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
