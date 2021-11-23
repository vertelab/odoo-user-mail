# -*- coding: utf-8 -*-

{
    'name': 'User mail client',
    'version': '14.0.1.0.0',
    'category': 'other',
    'summary': 'Administration of mail for users on client side',
    'description': """
    Client side configuration of mail accounts
    use this in /etc/odoo/openerp-server.conf:
    # mail_server
    passwd_server = localhost
    passwd_dbname = mail_server
    passwd_user = admin
    passwd_passwd = admin
    # for smtp-configuration
    smtp_host = localhost
    smtp_port = 8069
    smtp_encryption = yes
    smtp_user = admin
    smtp_pass = admin
    # for imap-configuration
    imap_host = localhost
    imap_port = 8069
    """,
    'author': 'Vertel AB',
    'website': 'https://www.vertel.se',
    'depends': ['user_password_tmp', 'fetchmail', 'user_mail_common'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_users_view.xml',
        'views/res_users_data.xml',
        'views/res_users_report.xml'
    ],
    'installable': True,
    'application': True,
}
