# -*- coding: utf-8 -*-
"""user_mail_ai.rule — användarens regler i klartext.

Utvärdering: deterministisk pre-filter (sender/subject/category) + LLM
för condition_kind='llm' (regeltexten injiceras i klassificeringsprompten).
Standing rules från ai.coworker.hitl-trust-ladder importeras med
source='trust_ladder'.

action_config-schema (JSON):

    create_object — skapa ett Odoo-objekt från mailet (deklarativt):
        {
          "model": "crm.lead",          # krävs — målmodell
          "defaults": {"type": "opportunity"},   # statiska fältvärden
          "partner": {                  # valfritt: hitta/skapa res.partner
            "mode": "link_or_create",  # link | create | link_or_create
            "create_company": true,     # skapa företag från domänen
            "contact_from_sender": true # skapa kontakt från avsändaren
          },
          "activity": {                 # valfritt: mail.activity på objektet
            "type": "Call",             # mail.activity.type-namn
            "summary": "Följ upp",
            "deadline_days": 2,
            "user": "owner"             # alltid mailägaren (self.user_id)
          },
          "hitl": true,                 # kräv godkännande (provläge)
          "llm_fields": {"name": "..."} # LLM-extraherade fält (filtreras)
        }

    create_activity — lägg en aktivitet på ett befintligt objekt:
        {
          "model": "res.partner",      # krävs (annars mailens kopplade objekt)
          "res_id": 123,                # valfritt (annars kopplat objekt)
          "activity": {...},            # som ovan
          "hitl": true
        }
"""

import json
import logging

from odoo import api, models, fields
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class UserMailAiRule(models.Model):
    _name = 'user_mail_ai.rule'
    _description = 'Mail-hjälpredan: användarregel'
    _order = 'priority, id'

    user_id = fields.Many2one(
        'res.users', string='Användare', required=True, ondelete='cascade',
        index=True, default=lambda self: self.env.user)
    name = fields.Char('Regel', required=True,
                       help='Klartext, t.ex. "arkivera nyhetsbrev jag inte öppnat"')
    priority = fields.Integer('Prioritet', default=10,
                              help='Lägre tal = högre prioritet.')
    active = fields.Boolean('Aktiv', default=True)
    condition_kind = fields.Selection([
        ('sender', 'Avsändare'),
        ('subject', 'Ämne'),
        ('category', 'Kategori'),
        ('llm', 'LLM (fri text)'),
    ], string='Villkorstyp', required=True, default='sender')
    condition_text = fields.Text('Villkor', required=True)
    action = fields.Selection([
        ('move_to_folder', 'Flytta till mapp'),
        ('flag', 'Flagga som viktig'),
        ('nudge', 'Nudgea mig'),
        ('ignore', 'Ignorera'),
        ('create_event', 'Skapa kalenderhändelse'),
        ('draft_reply', 'Dra svarsutkast'),
        ('block', 'Blockera'),
        ('send_to_specialist', 'Skicka till specialist'),
        ('create_object', 'Skapa Odoo-objekt'),
        ('create_activity', 'Skapa aktivitet'),
    ], string='Åtgärd', required=True)
    action_config = fields.Text(
        'Åtgärdskonfig (JSON)', default='{}',
        help='T.ex. {"folder": "AI/Arkiv"} för move_to_folder.\n'
             'create_object: {"model": "crm.lead", "defaults": {...}, '
             '"partner": {"mode": "link_or_create"}, '
             '"activity": {...}, "hitl": true, '
             '"llm_fields": {"name": "..."}}.\n'
             'create_activity: {"model": "res.partner", "activity": '
             '{...}, "hitl": true}.')
    source = fields.Selection([
        ('user', 'Användare'),
        ('seed', 'Default'),
        ('trust_ladder', 'Trust-ladder'),
    ], string='Källa', default='user', readonly=True)
    enforcement = fields.Selection([
        ('client', 'I Odoo (efter hämtning)'),
        ('server', 'På servern (Sieve)'),
    ], string='Verkställs', default='client', required=True,
        help='Var regeln körs.\n'
             'I Odoo: pollern hämtar mailet, AI:n klassificerar, sedan '
             'flyttas det. Regeln kan inte hindra mailet från att hamna i '
             'inkorgen, och den gör ingenting om pollern ligger nere.\n'
             'På servern: Dovecot kör regeln vid leverans. Bara villkor som '
             'Sieve förstår (avsändare, ämne) och åtgärder som Sieve klarar '
             '(flytta, flagga, kasta) — övriga avvisas när regeln sparas.')

    _sql_constraints = [
        ('unique_user_name', 'unique(user_id, name)',
         'Regelnamnet måste vara unikt per användare!'),
    ]

    @api.constrains('action', 'action_config')
    def _check_create_object_config(self):
        """create_object/create_activity requires a target model."""
        for rule in self:
            if rule.action not in ('create_object', 'create_activity'):
                continue
            cfg = rule._parse_config()
            if not cfg.get('model'):
                raise ValidationError(
                    'Regeln "%s" saknar "model" i action_config — '
                    'åtgärden %s kräver en målmodell.'
                    % (rule.name, rule.action))

    # ── Server-side (Sieve) ──────────────────────────────────────────────

    # Åtgärder som Sieve kan utföra. Allt annat kräver Odoo — en
    # kalenderhändelse, ett crm.lead, en aktivitet, en LLM-bedömning.
    SIEVE_ACTIONS = ('move_to_folder', 'flag', 'ignore', 'block')

    # Villkor som Sieve kan uttrycka. `category` är Odos klassificering
    # som bara finns EFTER att AI:n kört, och `llm` är en språkmodell.
    SIEVE_CONDITIONS = ('sender', 'subject')

    @api.constrains('enforcement', 'action', 'condition_kind')
    def _check_sieve_expressible(self):
        """Stoppa server-regler som Sieve inte kan utföra.

        Utan denna kontroll skulle en användare kunna sätta
        enforcement='server' på en regel som skapar ett crm.lead. Regeln
        skulle då tyst sluta fungera: kompilatorn hoppar över den, och
        _matching_rules() hoppar också över den (enforcement='server'),
        så INGEN skulle köra den. Användaren tror att regeln är aktiv.

        Hårt fel i stället för tyst nedgradering: en regel som inte kan
        köras där den påstås köra är värre än ingen regel.
        """
        for rule in self:
            if rule.enforcement != 'server':
                continue
            if rule.action not in self.SIEVE_ACTIONS:
                raise ValidationError(
                    'Regeln "%s" kan inte köras på servern: åtgärden "%s" '
                    'kräver Odoo.\n\nVälj "I Odoo (efter hämtning)" som '
                    'verkställighet, eller byt till en åtgärd som Sieve '
                    'klarar: flytta till mapp, flagga, ignorera.'
                    % (rule.name, dict(self._fields['action'].selection).get(
                        rule.action, rule.action)))
            if rule.condition_kind not in self.SIEVE_CONDITIONS:
                raise ValidationError(
                    'Regeln "%s" kan inte köras på servern: villkorstypen '
                    '"%s" går inte att uttrycka i Sieve.\n\nAnvänd '
                    'avsändare eller ämne, eller välj "I Odoo".'
                    % (rule.name, dict(
                        self._fields['condition_kind'].selection).get(
                            rule.condition_kind, rule.condition_kind)))

    # ── Synk till servern ────────────────────────────────────────────────

    def _sieve_resync(self):
        """Bygg om berörda användares Sieve-script.

        Tyst: ett trasigt Sieve-script får aldrig rulla tillbaka
        användarens regeländring. Felet hamnar i sieve.script
        (state=error, last_error) och syns i UI:t.
        """
        for user in self.mapped('user_id'):
            try:
                user._sieve_rebuild()
            except Exception as e:
                _logger.warning(
                    'Sieve-omsynk efter regeländring misslyckades för %s: %s',
                    user.name, e)

    @api.model_create_multi
    def create(self, vals_list):
        rules = super().create(vals_list)
        rules._sieve_resync()
        return rules

    def write(self, values):
        res = super().write(values)
        self._sieve_resync()
        return res

    def unlink(self):
        # Fånga användarna INNAN raderna försvinner — efter unlink() finns
        # ingen user_id kvar att synka.
        users = self.mapped('user_id')
        res = super().unlink()
        for user in users:
            try:
                user._sieve_rebuild()
            except Exception as e:
                _logger.warning(
                    'Sieve-omsynk efter borttagen regel misslyckades för '
                    '%s: %s', user.name, e)
        return res

    def _parse_config(self):
        try:
            cfg = json.loads(self.action_config or '{}')
            return cfg if isinstance(cfg, dict) else {}
        except Exception:
            return {}

    def _matches(self, mail):
        """Deterministisk matchning (sender/subject/category)."""
        ct = (self.condition_text or '').strip()
        if not ct:
            return False
        if self.condition_kind == 'sender':
            return ct.lower() in (mail.from_email or '').lower()
        if self.condition_kind == 'subject':
            return ct.lower() in (mail.subject or '').lower()
        if self.condition_kind == 'category':
            return ct == mail.category
        # llm matchas via klassificeringsutdata (matched_rules)
        return False
