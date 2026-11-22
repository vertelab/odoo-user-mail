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
"""res.users — fånga klartextlösenordet när det sätts.

VARFÖR DENNA FIL FINNS
======================

ManageSieve måste logga in med KLARTEXT. `dovecot_password` duger inte: det
är en SHA512-CRYPT-hash (enkelriktad, `sha512_crypt.hash()`), gjord för att
Dovecot ska kunna verifiera — inte för att vi ska kunna logga in.

Klartexten existerar bara i två ögonblick:
  1. när användaren byter lösenord (write() med password/new_password)
  2. när den genereras (user_mail_client:s lösenordsgenerator)

Denna modul fångar ögonblick 1 och sparar en tvåvägskrypterad kopia i
`sieve_password`. user_mail_imap gör sedan samma sak för IMAP-pollern i
`imap_password` — samma lösenord, samma Fernet-nyckel, två konsumenter.

VARFÖR INTE BARA imap_password?
-------------------------------
Därför att `user_mail_client` (där vacation-vyn sitter och där lösenordet
faktiskt byts) INTE beror på `user_mail_imap`. Om lösenordet bara fanns där
skulle vacation-synken aldrig få ett lösenord i en klient-only-installation.

Krypteringsnyckeln delas via ir.config_parameter `user_mail_imap.encryption_key`
om den finns (så vi inte har två nycklar för samma lösenord), annars skapas
`user_mail_common.encryption_key`.
"""

import logging

from odoo import _, api, models, fields
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover
    Fernet = None
    InvalidToken = Exception


class ResUsers(models.Model):
    _inherit = 'res.users'

    sieve_password = fields.Char(
        string='Sieve Password',
        help='Fernet-krypterad klartextkopia av e-postlösenordet. '
             'Används av ManageSieve. Sätts automatiskt när lösenordet '
             'byts — fyll aldrig i för hand.')

    # ── Nyckel ───────────────────────────────────────────────────────────

    @api.model
    def _sieve_encryption_key(self):
        """Fernet-nyckel, delad med user_mail_imap när den finns.

        Att återanvända `user_mail_imap.encryption_key` är avsiktligt: det
        är SAMMA lösenord som krypteras, och två nycklar för samma hemlighet
        är en driftfälla (rotera den ena, glöm den andra).
        """
        if Fernet is None:
            raise UserError(_(
                'Python-paketet cryptography saknas — kan inte kryptera '
                'lösenordet.'))
        icp = self.env['ir.config_parameter'].sudo()
        for param in ('user_mail_imap.encryption_key',
                      'user_mail_common.encryption_key'):
            key = icp.get_param(param)
            if key:
                return key
        key = Fernet.generate_key().decode()
        icp.set_param('user_mail_common.encryption_key', key)
        return key

    # ── Kryptografi ──────────────────────────────────────────────────────

    def _encrypt_sieve_pw(self, password):
        f = Fernet(self._sieve_encryption_key().encode())
        return f.encrypt(password.encode()).decode()

    def _decrypt_sieve_pw(self):
        """Klartext eller None. Kastar aldrig — trasig nyckel ger None."""
        self.ensure_one()
        if not self.sieve_password or Fernet is None:
            return None
        try:
            f = Fernet(self._sieve_encryption_key().encode())
            return f.decrypt(self.sieve_password.encode()).decode()
        except (InvalidToken, Exception) as e:
            _logger.warning(
                'Kunde inte dekryptera sieve_password för %s: %s',
                self.login, e)
            return None

    # ── Fånga lösenordet ─────────────────────────────────────────────────

    def write(self, values):
        """Spara en krypterad kopia när lösenordet sätts.

        Odoo tar bort `password` ur values innan det når databasen, så vi
        måste läsa det HÄR — efter att super() kört finns klartexten inte
        kvar någonstans.

        Vi rör inte `dovecot_password` eller `imap_password`: de ägs av
        user_mail_client respektive user_mail_imap. Vi lägger bara till vår
        egen kopia.
        """
        password = values.get('password') or values.get('new_password')
        res = super().write(values)
        if password:
            try:
                encrypted = self._encrypt_sieve_pw(password)
            except UserError as e:
                # cryptography saknas — låt inte det stoppa ett lösenbyte.
                _logger.warning('Kunde inte spara sieve_password: %s', e)
            else:
                # super().write igen med bara vårt fält: inga rekursioner
                # eftersom `password` inte finns i values denna gång.
                super(ResUsers, self).write({'sieve_password': encrypted})
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """Fånga lösenordet även vid skapande."""
        passwords = [v.get('password') or v.get('new_password')
                     for v in vals_list]
        users = super().create(vals_list)
        for user, password in zip(users, passwords):
            if not password:
                continue
            try:
                encrypted = user._encrypt_sieve_pw(password)
            except UserError as e:
                _logger.warning('Kunde inte spara sieve_password: %s', e)
            else:
                super(ResUsers, user).write({'sieve_password': encrypted})
        return users

    # ── Override för ManageSieve ─────────────────────────────────────────

    def _sieve_password(self):
        """Klartextslösenord för ManageSieve.

        Ordning:
          1. `sieve_password` — denna moduls kopia (sätts vid lösenbyte)
          2. `imap_password` — om user_mail_imap är installerad och har en
             dekrypteringsmetod (samma lösenord, annan konsument)

        Steg 2 finns för användare vars lösenord sattes innan denna modul
        installerades: deras `sieve_password` är tom men `imap_password`
        kan vara satt. Utan fallbacken skulle de behöva byta lösenord
        innan vacation fungerar.
        """
        self.ensure_one()
        pw = self._decrypt_sieve_pw()
        if pw:
            return pw
        decrypt_imap = getattr(self, '_decrypt_imap_pw', None)
        if callable(decrypt_imap):
            return decrypt_imap()
        return None
