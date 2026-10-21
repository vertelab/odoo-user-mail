{
    'name': 'User Mail: IMAP Client',
    # Versionsbokföring: 18.0 = Odoo-version, 1 = major (ej
    # regressionsbar), 10 = minor, 2 = buggfixar. 10.3 = stjärnfiltret
    # söker nu i hela mappen, etikettmenyn på meddelandet och
    # olästfiltret som egen axel (fix-flag-search-and-message-labels).
    'version': '18.0.1.10.3',
    'summary': 'IMAP email client integrated in Odoo — with per-user poller.',
    'description': '''
IMAP Client
===========

    IMAP email client integrated in Odoo — with per-user poller.

    Features:

        - Web integration: Exposes HTTP endpoints for external systems.
        - Automation: Scheduled jobs: User Mail: IMAP Poll (hjälpredan).
        - Guided Wizards: Step-by-step dialogs for data entry.
        - UI Integration: Extends 1 view(s) in the Odoo interface.
        - Extends Odoo: Builds on user.mail.imap, user.mail.poll, user.mail.processed.
    ''',
    'category': 'Productivity',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se/apps/odoo-user-mail/user_mail_imap',
    'license': 'AGPL-3',
    'depends': ['user_mail_common', 'mail', 'web', 'calendar'],
    'external_dependencies': {
        'python': ['cryptography', 'icalendar'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'data/spam_headers.xml',
        # Wizarden FÖRE vyn: res_users_view.xml refererar
        # %(action_imap_password_wizard)d och kräver att den finns.
        'wizards/imap_password_wizard.xml',
        'views/menus_views.xml',
        'views/res_users_view.xml',
        # Fylld markör i user_mail_clients fristående E-postinställningar.
        # Måste laddas EFTER user_mail_client — se views/own_settings/.
        'views/own_settings/res_users_view.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'user_mail_imap/static/src/services/imap_store.esm.js',
            'user_mail_imap/static/src/js/mail_flags.esm.js',
            'user_mail_imap/static/src/js/mail_imap.esm.js',
            'user_mail_imap/static/src/xml/mail_imap.xml',
            'user_mail_imap/static/src/components/folder_tree/folder_tree.esm.js',
            'user_mail_imap/static/src/components/folder_tree/folder_tree.xml',
            'user_mail_imap/static/src/components/mail_list/mail_list.esm.js',
            'user_mail_imap/static/src/components/mail_list/mail_list.xml',
            'user_mail_imap/static/src/components/mail_search/mail_search.esm.js',
            'user_mail_imap/static/src/components/mail_search/mail_search.xml',
            'user_mail_imap/static/src/components/mail_detail/mail_detail.esm.js',
            'user_mail_imap/static/src/components/mail_detail/mail_detail.xml',
            'user_mail_imap/static/src/components/sieve_rule_dialog/sieve_rule_dialog.esm.js',
            'user_mail_imap/static/src/components/sieve_rule_dialog/sieve_rule_dialog.xml',
            'user_mail_imap/static/src/components/composer/composer.esm.js',
            'user_mail_imap/static/src/components/composer/composer.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
