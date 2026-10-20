# -*- coding: utf-8 -*-
"""Konkret modell som ir.cron pekar på för IMAP-pollning.

user.mail.imap är abstract — ir.cron behöver en konkret modell. All logik
ligger i user.mail.imap.action_poll_all(); denna modell är bara en
cron-anknytning plus en hälsobild som övervakningen kan läsa.
"""

import logging

from odoo import models, api, fields

_logger = logging.getLogger(__name__)


class UserMailPoll(models.Model):
    _name = 'user.mail.poll'
    _description = 'IMAP Poller (cron-anknytning)'

    @api.model
    def _poll_cron(self):
        """Cron-entry: polla alla användare med imap_poll_enabled=True."""
        return self.env['user.mail.imap'].action_poll_all()

    @api.model
    def _poll_health(self):
        """Hälsa per pollande användare — för övervakning, inte för logg-grep.

        Incidenten 2026-10-19 hade MTTD > 48 h eftersom `active (running)`
        såg friskt ut medan pollern aldrig blev klar. Den här metoden ger
        övervakningen samma information som loggen, utan att läsa loggen.

        Returns dict: {user_login: {last_run, last_ok, truncated,
                                    parse_errors_24h, spam_skipped_24h,
                                    backlog_estimate}}
        """
        users = self.env['res.users'].sudo().search(
            [('imap_poll_enabled', '=', True)])
        since = fields.Datetime.subtract(fields.Datetime.now(), hours=24)
        Processed = self.env['user.mail.processed'].sudo()
        out = {}
        for user in users:
            # Bara `failed` är ett fel. Ett spam-överhopp har
            # `failed=False` + `skip_reason='spam'` och får aldrig öka
            # parse_errors — det är ett förväntat utfall.
            parse_errors = Processed.search_count([
                ('user_id', '=', user.id),
                ('failed', '=', True),
                ('skip_reason', '=', False),
                ('processed_at', '>=', since),
            ])
            spam_skipped = Processed.search_count([
                ('user_id', '=', user.id),
                ('skip_reason', '=', 'spam'),
                ('processed_at', '>=', since),
            ])
            out[user.login] = {
                'last_run': user.last_imap_sync,
                'last_ok': user.last_imap_sync if not parse_errors else False,
                # Cursor saknas ⇒ nästa körning gör en full omsynkronisering.
                'truncated': not user.last_imap_uid,
                'parse_errors_24h': parse_errors,
                'spam_skipped_24h': spam_skipped,
                'backlog_estimate': 0,
            }
        return out
