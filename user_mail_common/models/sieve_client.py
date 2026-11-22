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
"""ManageSieve-klient (RFC 5804) — tunn wrapper runt sievelib.

Två saker som inte är uppenbara:

1. **Lösenordet finns inte i denna modul.** `dovecot_password` är en
   SHA512-CRYPT-hash (enkelriktad) och duger inte för inloggning. Klartexten
   ligger Fernet-krypterad i `imap_password`, som definieras i
   `user_mail_imap` — en modul som BEROR på user_mail_common, inte tvärtom.
   Vi kan därför inte läsa fältet härifrån. `_password()` anropar istället
   `_sieve_password()` som user_mail_imap overridar. Utan den override:n
   returneras None och synken failar med ett tydligt fel — aldrig tyst.

2. **checkscript är inte valfritt.** `sievelib.parser` validerar syntax
   lokalt, men servern kan avvisa av skäl parsern inte känner till
   (saknad `require`, otillåten tagg). En trasig AKTIV sieve-regel får
   Dovecot att avvisa eller felsortera post — därför kompileras scriptet
   alltid på servern med CHECKSCRIPT innan PUTFILE.
"""

import logging

import odoo
from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_PORT = 4190


class SieveClient(models.AbstractModel):
    """ManageSieve-anslutning för en användare."""

    _name = 'sieve.client'
    _description = 'ManageSieve client'

    # ── Anslutningsparametrar ────────────────────────────────────────────

    def _sieve_config(self, key, default=None):
        return self.env['ir.config_parameter'].sudo().get_param(
            'user_mail_common.%s' % key, default)

    def _sieve_host(self):
        """ManageSieve-värd.

        Faller tillbaka på `imap_host` — ManageSieve körs normalt på samma
        maskin som IMAP. Att kräva en separat parameter vore att be
        användaren konfigurera samma sak två gånger.

        Läser `imap_host` från BÅDA källorna: `ir.config_parameter` och
        `odoo.tools.config` (odoo.conf). IMAP-klienten hämtar sin värd ur
        odoo.conf (imap_server._get_config → odoo.tools.config), medan
        den här modulen historiskt bara tittade i ir.config_parameter.
        På en installation där imap_host bara står i odoo.conf blev
        resultatet att IMAP fungerade men Sieve försökte mot localhost —
        med 'Connection refused' som enda ledtråd. Samma nyckel ska
        betyda samma sak i båda modulerna.
        """
        icp = self.env['ir.config_parameter'].sudo()
        return (self._sieve_config('sieve_host')
                or icp.get_param('imap_host')
                or odoo.tools.config.get('imap_host')
                or 'localhost')

    def _sieve_port(self):
        return int(self._sieve_config('sieve_port') or DEFAULT_PORT)

    def _sieve_starttls(self):
        """STARTTLS är standard. Port 4190 är klartext tills STARTTLS sagts."""
        return self._sieve_config('sieve_starttls', 'True') != 'False'

    def _sieve_login(self, user):
        login = user.postfix_mail or user.login
        if not login:
            raise UserError(_(
                'Användaren %s saknar e-postadress (postfix_mail) — '
                'ManageSieve kan inte logga in.', user.name))
        return login

    def _sieve_password(self, user):
        """Klartextslösenord för ManageSieve — hämtas från användaren.

        Lösenordet ägs av `res.users` (fältet `sieve_password`, satt av
        write()-hooken i res_users_password.py, med fallback till
        `imap_password` när user_mail_imap är installerad). Denna modell
        är bara en transport och ska inte ha en egen kopia av logiken —
        därför delegerar vi.

        Returnerar None om användaren inte har något lösenord; anroparen
        måste hantera det, aldrig gissa.
        """
        return user._sieve_password()

    # ── Anslutning ───────────────────────────────────────────────────────

    def _connect(self, user):
        """Öppna en autentiserad ManageSieve-anslutning.

        Anroparen ansvarar för att stänga den (logout i finally).
        """
        try:
            from sievelib.managesieve import Client
        except ImportError:
            raise UserError(_(
                'Python-paketet sievelib saknas. Installera det med '
                'repo_apply (requirements.txt i odoo-user-mail) eller '
                'pip3 install sievelib.'))

        password = self._sieve_password(user)
        if not password:
            raise UserError(_(
                'Inget lösenord tillgängligt för ManageSieve för %s. '
                'Lösenordet lagras av user_mail_imap (imap_password); '
                'modulen måste vara installerad och lösenordet satt.',
                user.name))

        client = Client(self._sieve_host(), self._sieve_port())
        try:
            ok = client.connect(
                self._sieve_login(user), password,
                starttls=self._sieve_starttls())
        except Exception as e:
            raise UserError(_(
                'Kunde inte ansluta till ManageSieve på %(host)s:%(port)s: '
                '%(err)s',
                host=self._sieve_host(), port=self._sieve_port(), err=e))
        if not ok:
            raise UserError(_(
                'ManageSieve avvisade inloggningen för %(login)s på '
                '%(host)s:%(port)s.',
                login=self._sieve_login(user),
                host=self._sieve_host(), port=self._sieve_port()))
        return client

    # ── Operationer ──────────────────────────────────────────────────────

    def _checkscript(self, client, script):
        """Låt servern kompilera scriptet. True = OK.

        Detta är den enda kontroll som betyder något i praktiken: den
        fångar saknade require-satser och taggar som den lokala parsern
        accepterar men Pigeonhole inte.
        """
        try:
            return bool(client.checkscript(script))
        except Exception as e:
            _logger.warning('Sieve CHECKSCRIPT kastade: %s', e)
            return False

    def _server_error(self, client):
        """Plocka ut serverns feltext (bytes) som sträng."""
        msg = getattr(client, 'errmsg', None) or b''
        if isinstance(msg, bytes):
            msg = msg.decode('utf-8', 'replace')
        return (msg or '').strip()

    def _listscripts(self, client):
        """(aktivt_script, [övriga]) enligt RFC 5804."""
        try:
            return client.listscripts()
        except Exception as e:
            raise UserError(_('Kunde inte lista Sieve-script: %s', e))

    def _getscript(self, client, name):
        try:
            return client.getscript(name)
        except Exception as e:
            raise UserError(_('Kunde inte läsa Sieve-scriptet %s: %s',
                              name, e))

    def _putscript(self, client, name, body):
        """Ladda upp ett script utan att aktivera det."""
        try:
            ok = client.putscript(name, body)
        except Exception as e:
            raise UserError(_('Kunde inte ladda upp Sieve-scriptet %s: %s',
                              name, e))
        if not ok:
            raise UserError(_(
                'Servern avvisade Sieve-scriptet %(name)s: %(err)s',
                name=name, err=self._server_error(client) or _('okänt fel')))
        return True

    def _setactive(self, client, name):
        try:
            ok = client.setactive(name)
        except Exception as e:
            raise UserError(_('Kunde inte aktivera Sieve-scriptet %s: %s',
                              name, e))
        if not ok:
            raise UserError(_(
                'Servern kunde inte aktivera %(name)s: %(err)s',
                name=name, err=self._server_error(client) or _('okänt fel')))
        return True

    def _deletescript(self, client, name):
        try:
            return client.deletescript(name)
        except Exception as e:
            raise UserError(_('Kunde inte ta bort Sieve-scriptet %s: %s',
                              name, e))
