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
