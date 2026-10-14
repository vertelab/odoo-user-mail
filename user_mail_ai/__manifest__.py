# -*- coding: utf-8 -*-
{
    'name': 'User Mail: AI Assistant',
    'version': '18.0.1.8.0',
    'summary': 'Personlig AI-mailhjälpreda — IMAP-triage, Odoo Mind (graf), Teams→kalender',
    'category': 'Productivity',
    'author': 'Vertel Sverige AB',
    'website': 'https://vertel.se/apps/odoo-user-mail/user_mail_ai',
    'license': 'AGPL-3',
    'description': '''
AI Assistant
============

    Personal AI assistant for mail (ai.coworker "Mail Assistant").

    - Poller piggyback: inherits user.mail.imap and consumes normalised mail
      via _on_new_messages().
    - Triage: classifies incoming mail and suggests actions.
    - Rules (user_mail_ai.rule): seven illustrative seed rules copied to
      each user when IMAP polling is enabled:
        1. Teams invites -> calendar event (category/create_event)
        2. Newsletters -> AI/Newsletters (category/move_to_folder)
        3. Needs action -> nudge me (llm/nudge)
        4. Quote request -> opportunity (llm/create_object -> crm.lead)
        5. Help request from known partner -> ticket
           (llm/create_object -> helpdesk.ticket)
        6. Vendor invoice -> bookable entry
           (llm/create_object -> account.move)
        7. Meeting notes -> knowledge note
           (llm/create_object -> joplin.note)

    Rules 4-7 create Odoo objects and are created INACTIVE in probe mode:
    the user activates the rule and each object creation goes through HITL
    until the user explicitly sets action_config.hitl=false. There is no
    automatic trust ladder.
    ''',
    'depends': [
        'user_mail_imap',
        'user_mail_common',
        'ai_agent_core',
        'calendar',
        'crm',
        'helpdesk_mgmt',
        'account',
        'knowledge_joplin',
    ],
    'external_dependencies': {
        'python': ['icalendar'],
    },
    'data': [
        'security/ir.model.access.csv',
        'security/rules.xml',
        'security/rules_ai.xml',
        'data/mail_coworker.xml',
        'data/mail_routing.xml',
        'data/mail_rules_defaults.xml',
        'data/mail_intelligence_skills.xml',
        'data/cron_intelligence.xml',
        'data/cron_memory_sync.xml',
        'data/graph_mail_node.xml',
        'views/user_mail_ai_mail_views.xml',
        'views/user_mail_ai_rule_views.xml',
        'views/res_users_mail_ai_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
