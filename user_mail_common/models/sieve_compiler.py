# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2026 Vertel Sverige AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
"""Sieve-kompilering: vacation + (senare) regler → ett script.

VARFÖR EN SAMMANSTÄLLARE OCH INTE BARA STRÄNGAR
==============================================

Ett Sieve-script har EN `require`-sats i toppen som måste lista varje
extension som används någonstans i filen. Om vacation lägger till
`require ["vacation"]` och reglerna lägger till
`require ["fileinto", "imap4flags"]` får vi antingen dubbla require-satser
(ogiltigt) eller en som saknar något (servern avvisar).

Därför byggs scriptet i två steg:
  1. Varje del (vacation, regler) returnerar sin kod OCH sina extensions.
  2. `assemble()` slår ihop extensions till EN require-sats och fogar
     delarna efter.

Det gör också att vacation kan läggas till/ tas bort utan att röra
reglerna — vilket är precis vad cron behöver.
"""

import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Ping-pong-skydd: Pigeonhole svarar högst EN gång per avsändare per N dagar.
# Detta är det primära loppskyddet i vacation — se design.md. Utan det kan
# två autosvarande parter svara varandra i all oändlighet.
VACATION_DAYS = 7


class SieveCompiler(models.AbstractModel):
    """Bygger Sieve-kod ur Odoo-data."""

    _name = 'sieve.compiler'
    _description = 'Sieve compiler'

    # ── Hjälp ────────────────────────────────────────────────────────────

    @staticmethod
    def quote(value):
        """Citera en Sieve-sträng (RFC 5228 §2.4.2).

        Backslash och citattecken escapas; resten lämnas. Newlines är
        ogiltiga i en quoted string — de ersätts med mellanslag, annars
        kraschar hela scriptet för att användaren tryckt Enter i sin
        semestertext.
        """
        if value is None:
            return '""'
        text = str(value).replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
        text = text.replace('\\', '\\\\').replace('"', '\\"')
        return '"%s"' % text

    # ── Vacation ─────────────────────────────────────────────────────────

    def vacation_block(self, user):
        """Vacation-kod för en användare, eller (None, []) om ingen.

        Returnerar (kod, [extensions]). Koden är en komplett `if`-sats —
        eller None när vacation inte ska vara aktiv.

        VIKTIGT om :from — utan den blir avsändaren postmaster
        (`postmaster_address = support@vertel.se` i Dovecot). Användarens
        autosvar ska komma från användaren själv, så :from sätts alltid när
        adressen finns. Servern accepterar taggen (verifierat med
        CHECKSCRIPT mot imap.vertel.se:4190).
        """
        user.ensure_one()
        if not user.vacation_active:
            return None, []

        sender = user.postfix_mail
        if not sender or '@' not in sender or sender.endswith('@False'):
            # `_email()` bygger postfix_mail som '<login>@<domain>'. Saknas
            # company_id.domain blir resultatet 'nisse@False' — ett
            # befintligt fel i _email(), men det får inte slå igenom här:
            # ett vacation :from med '@False' är en ogiltig adress och
            # autosvaret skulle komma från postmaster ändå.
            _logger.warning(
                'Vacation aktiv för %s men postfix_mail är ogiltig (%r) — '
                'hoppar över. Sätt företagets domän.', user.name, sender)
            return None, []

        subject = user.vacation_subject or _('Semester')
        text = user.vacation_text or ''

        parts = [
            'vacation',
            ':days %d' % VACATION_DAYS,
            ':from %s' % self.quote(sender),
            ':subject %s' % self.quote(subject),
            self.quote(text),
        ]
        code = (
            '# Vacation — %s\n'
            '# :days %d ar loppskyddet: hogst ett svar per avsandare\n'
            '# och period. Andra inte utan att veta vad du gor.\n'
            'if true {\n'
            '    %s;\n'
            '}\n'
        ) % (user.name, VACATION_DAYS, ' '.join(parts))
        return code, ['vacation']

    # ── Sammansattning ───────────────────────────────────────────────────

    def assemble(self, parts):
        """Sätt ihop (kod, extensions)-par till ett giltigt script.

        `parts` är en lista av tupler. Tomma delar hoppas över. Om inget
        återstår returneras ett minimalt `keep;` — ett tomt script är
        ogiltigt och skulle få Dovecot att avvisa post.

        Extension-listan dedupliceras och sorteras så att samma indata
        alltid ger samma utdata (annars blir varje synk en ändring).
        """
        codes = []
        extensions = set()
        for code, exts in parts:
            if not code:
                continue
            codes.append(code.rstrip())
            extensions.update(exts or [])

        if not codes:
            return 'keep;\n'

        require = ''
        if extensions:
            require = 'require [%s];\n\n' % ', '.join(
                self.quote(e) for e in sorted(extensions))
        return require + '\n'.join(codes) + '\n'

    # ── Regler ───────────────────────────────────────────────────────────

    # Villkor som går att uttrycka i Sieve. `category` och `llm` gör det
    # INTE — category är en Odoo-klassificering som bara finns efter att
    # AI:n kört, och llm är per definition en språkmodell. De stannar
    # klientsidan; se user_mail_ai.rule.enforcement.
    CONDITION_MAP = {
        'sender': 'from',
        'subject': 'subject',
    }

    def rules_part(self, rules):
        """(kod, extensions) för en uppsättning server-regler.

        Reglerna kompileras med sievelib.factory.FiltersSet — att bygga
        Sieve-strängar för hand är hur man får felciterade mappnamn.

        FYRA FÄLLOR, alla verifierade mot imap.vertel.se:4190:

        1. Villkor skickas som (header-namn, operator, värde), INTE
           ('header', ':contains', ...). `header` är test-kommandot som
           sievelib bygger internt; att skicka det som namn ger
           BadArgument.

        2. Mappnamn skickas OCITERAT ('INBOX.Linkedin mm'). sievelib
           citerar själv — skickar man '"INBOX.X"' blir resultatet
           "\\"INBOX.X\\"", dvs dubbelt escapat och en mapp som inte finns.

        3. :days tar en INT, inte en sträng (BadValue).

        4. FiltersSet.tosieve() skriver sin EGEN require-sats. Vi plockar
           ut extensions ur fs.requires och strippar require-raden, så att
           assemble() kan slå ihop dem med vacation. Två require-satser i
           samma script är ogiltigt.
        """
        rules = rules.filtered(lambda r: r.enforcement == 'server')
        if not rules:
            return None, []

        try:
            from sievelib.factory import FiltersSet
        except ImportError:
            raise UserError(_('Python-paketet sievelib saknas.'))

        fs = FiltersSet('odoo_ai')
        used = 0
        for rule in rules.sorted(lambda r: (r.priority, r.id)):
            conditions = self._rule_conditions(rule)
            actions = self._rule_actions(rule)
            if not conditions or not actions:
                continue
            fs.addfilter(rule.name, conditions, actions)
            used += 1

        if not used:
            return None, []

        import io
        buf = io.StringIO()
        fs.tosieve(buf)
        body = buf.getvalue()

        # Strippa require-raden som FiltersSet lade till — assemble()
        # bygger en gemensam. Regexen matchar bara den inledande satsen.
        import re
        body = re.sub(r'^require\s*\[[^\]]*\]\s*;\s*\n\s*\n?', '', body)

        return body.rstrip() + '\n', list(fs.requires)

    def _rule_conditions(self, rule):
        """Sieve-villkor för en regel, eller [] om den inte kan uttryckas."""
        header = self.CONDITION_MAP.get(rule.condition_kind)
        if not header:
            # category/llm — klientsida, hoppa över tyst. Detta är inte en
            # bugg: _apply_rules() hanterar dem.
            return []
        text = (rule.condition_text or '').strip()
        if not text:
            return []
        return [(header, ':contains', text)]

    def _rule_actions(self, rule):
        """Sieve-åtgärder för en regel, eller [] om de inte kan uttryckas."""
        cfg = rule._parse_config()
        if rule.action == 'move_to_folder':
            folder = cfg.get('folder')
            if not folder:
                return []
            # :create skapar mappen om den inte finns — annars avvisar
            # Dovecot fileinto med "Mailbox does not exist" och mailet
            # blir kvar i INBOX utan spår.
            return [('fileinto', ':create', folder)]
        if rule.action == 'flag':
            return [('addflag', '\\Flagged')]
        if rule.action in ('ignore', 'block'):
            return [('discard',)]
        # nudge, draft_reply, create_object, create_activity, create_event,
        # send_to_specialist — kräver Odoo, kan inte köras i Sieve.
        return []
