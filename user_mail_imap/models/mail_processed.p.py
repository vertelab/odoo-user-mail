# -*- coding: utf-8 -*-
"""Beständig dedup för IMAP-pollern — processade Message-ID:n per användare."""

import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class UserMailProcessed(models.Model):
    _name = 'user.mail.processed'
    _description = 'Processed Mail Message-ID (poller dedup)'
    _order = 'processed_at desc'

    user_id = fields.Many2one(
        'res.users', string='Användare', required=True,
        ondelete='cascade', index=True)
    message_id = fields.Char(
        string='Message-ID / dedup-nyckel', required=True, index=True)
    processed_at = fields.Datetime(
        string='Processad', default=fields.Datetime.now)
    failed = fields.Boolean(
        string='Misslyckad', default=False, index=True,
        help='Satt när meddelandet inte kunde bearbetas (t.ex. '
             'normaliseringsfel). Raden finns ändå — cursorn ska kunna '
             'avancera förbi ett trasigt meddelande.')
    failure_reason = fields.Char(
        string='Felorsak',
        help='Undantagsklass och feltext, för felsökning utan att läsa loggen.')
    skip_reason = fields.Char(
        string='Överhoppad orsak',
        help='Satt när meddelandet medvetet hoppades över, t.ex. "spam". '
             'Skiljer ett förväntat utfall från ett fel: bara `failed` '
             'räknas som parse-fel i pollerns hälsomätvärde.')

    _sql_constraints = [
        ('unique_user_message',
         'unique(user_id, message_id)',
         'Message already processed for this user!'),
    ]
