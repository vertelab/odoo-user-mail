# -*- coding: utf-8 -*-
"""Per-användare-koppling: vilken hjälpreda tjänar användaren."""

import logging

from odoo import models, fields

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    ai_coworker_id = fields.Many2one(
        'ai.coworker', string='AI Medarbetare (mail)',
        help='Hjälpredan som tjänar denna användare. Tomt → default '
             'Mail-hjälpredan används.')
    # ── Skiva 3: intresseprofil + digest ──
    ai_profile_text = fields.Text('Intresseprofil (genererad)')
    ai_profile_embedding = fields.Text('Profil-embedding (JSON)')
    ai_profile_updated = fields.Datetime('Profil uppdaterad')
    ai_profile_weekday = fields.Selection([
        ('0', 'Måndag'), ('1', 'Tisdag'), ('2', 'Onsdag'),
        ('3', 'Torsdag'), ('4', 'Fredag'), ('5', 'Lördag'),
        ('6', 'Söndag'),
    ], string='Veckodag för profilomräkning', default='4',
        help='Dagen då intresseprofilen räknas om (cron kör dagligen).')
    ai_digest_enabled = fields.Boolean('Daglig digest', default=False)
    ai_digest_weekday = fields.Selection([
        ('0', 'Måndag'), ('1', 'Tisdag'), ('2', 'Onsdag'),
        ('3', 'Torsdag'), ('4', 'Fredag'), ('5', 'Lördag'),
        ('6', 'Söndag'),
    ], string='Veckodigest dag', default='4')

    ai_newsletter_move_enabled = fields.Boolean(
        'Flytta nyhetsbrev automatiskt', default=False,
        help='Sätts via HITL-godkännande (Skiva 2). Ersätts av regelmodellen '
             'i Skiva 3.')

    def write(self, values):
        """Aktiverad pollning → se till att användaren har sina seed-regler.

        Utan detta får en ny användare aldrig sina regler (modul-install/
        update kör bara _ensure_default_rules en gång). Idempotent.
        """
        res = super().write(values)
        if values.get('imap_poll_enabled'):
            try:
                self.env['user_mail_ai.mail']._ensure_default_rules()
            except Exception as e:
                _logger.warning(
                    'Seed-regler kunde inte skapas vid aktivering: %s', e)
        return res

    def action_open_mail_rules(self):
        """Smartknapp (Min profil): öppna mina mail-regler."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Mina mail-regler',
            'res_model': 'user_mail_ai.rule',
            'view_mode': 'list,form',
            'domain': [('user_id', '=', self.id)],
        }

    def action_refresh_mail_memory(self):
        """Min profil: bygg minnet för mina ännu ej indexerade mail.

        Kör samma kärna som cronen (_refresh_memory) men scopad till
        env.user — rör aldrig någon annan användares mail.

        Meddelandet skiljer på de tre lägena (2026-10-14): allt redan
        synkat, något synkat nu, eller misslyckat. Förr stod det "0 mail
        synkades" i alla tre — vilket dolde både färdigt arbete och fel.
        """
        self.ensure_one()
        Mail = self.env['user_mail_ai.mail']
        stats = Mail.with_user(self)._refresh_memory(self)
        synced = stats.get('synced', 0)
        failed = stats.get('failed', 0)
        pending = stats.get('pending', 0)
        total = stats.get('total', 0)

        if synced and not failed:
            notif_type = 'success'
        elif failed:
            notif_type = 'warning'
        else:
            notif_type = 'info'

        parts = []
        if synced:
            parts.append('%s mail indexerades.' % synced)
        if failed:
            parts.append('%s misslyckades (se loggen).' % failed)
        if pending:
            parts.append('%s återstår — kör igen.' % pending)
        if not parts:
            parts.append('Alla %s mail är redan indexerade.' % total)
        parts.append('(%s av %s indexerade.)' % (total - pending, total))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Mail-minne uppdaterat',
                'message': ' '.join(parts),
                'type': notif_type,
                'sticky': bool(failed),
            },
        }
