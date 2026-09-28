# -*- coding: utf-8 -*-
{
    'name': 'E-post i Vertel',
    'version': '18.0.1.0.0',
    'summary': 'Onboardingskurs: e-postklienten (IMAP/SMTP) och webmail',
    'description': """
Lär dig koppla upp din e-post, läsa och skicka, och använda AI-assistenten i inkorgen.
""",
    'author': 'Vertel AB',
    'website': 'https://vertel.se',
    'license': 'LGPL-3',
    'category': 'Website/eLearning',
    'depends': ['website_slides'],
    'data': [
        'views/slide_channel_data.xml',
    ],
    'demo': [
        'demo/slide_slide_demo.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
