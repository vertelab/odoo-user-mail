# -*- coding: utf-8 -*-
{
    'name': 'User SCIM — Admin Directory',
    'version': '18.0.1.0.0',
    'category': 'Tools',
    'summary': 'Central admin view of all LDAP users across customers',
    'description': """
User SCIM — Admin Directory
=============================
Central vy i ledningssystemet som visar ALLA användare från ALLA kunder
i den gemensamma LDAP-katalogen.

Visar data som synkas via SCIM-bridgen från respektive kunds Odoo-instans.

Funktioner:
- Trädvy över alla LDAP-användare med kundtillhörighet
- Filter på kund, aktiv, har Matrix-ID, m.fl.
- Konfliktdetektering (samma uid i flera kunder)
- Dashboard med statistik per kund
- Manuell synk från SCIM-bridge

Installeras ENDAST på ledningssystemets Odoo, inte på kundinstanser.

Beroenden: user_scim (för återanvändning av SCIM-funktioner)
    """,
    'author': 'Vertel AB',
    'website': 'https://vertel.se',
    'license': 'AGPL-3',
    'depends': [
        'base',
        'user_scim',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'views/scim_directory_views.xml',
        'views/scim_directory_kanban.xml',
        'views/scim_directory_menus.xml',
        'views/res_config_settings_view.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
