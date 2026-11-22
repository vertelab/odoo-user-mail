# -*- coding: utf-8 -*-
"""Poller-piggyback: ärv user.mail.imap och konsumera normaliserade mail."""

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class UserMailImapAI(models.AbstractModel):
    _inherit = 'user.mail.imap'

    def _on_new_messages(self, messages):
        """Konsumera normaliserade mail → triage-pipeline (ingest → klass → dispatch).

        Körs i användarens kontext (with_user) — env.user är ägaren.
        """
        Mail = self.env['user_mail_ai.mail']
        ingested = 0
        for msg in messages:
            try:
                triage = Mail._ingest_message(msg, user=self.env.user)
                if triage:
                    ingested += 1
            except Exception as e:
                _logger.error(
                    'Mail ingest failed for %s (%s): %s',
                    msg.get('subject', '?'), self.env.user.login, e)
        if ingested:
            try:
                Mail._process_new_for_user(self.env.user)
            except Exception as e:
                _logger.error('Mail pipeline failed for %s: %s',
                              self.env.user.login, e)
        # Kön ska vara tom när batchen är konsumerad. Det som ligger kvar
        # hör till mail som inte kunde ingesteras — att hålla dem kvar
        # vore att läcka minne i modulnivå-state.
        Mail._clear_raw_stash()
        return ingested

    def _on_new_message_raw(self, norm, raw_bytes):
        """Arkivera `.eml` medan råbytesen ännu finns i handen.

        Pollern anropar denna via `raw_sink` INNAN det normaliserade mailet
        läggs i listan. Att skriva bilagan här i stället för i ingest gör att
        poll av N mail inte behöver bära N meddelanden i minnet samtidigt
        (INC-2026-10-19: RSS 500 MB -> 2 336 MB på sju minuter).

        Bilagan kopplas till `user_mail_ai.mail`-posten när den skapas i
        ingest — här lagras bytesen på en kö som ingest plockar upp via
        meddelandets `message_id`.
        """
        if not raw_bytes:
            return
        message_id = (norm.get('message_id') or norm.get('dedup_key') or '')
        if not message_id:
            return
        self.env['user_mail_ai.mail']._stash_raw(message_id, raw_bytes)
