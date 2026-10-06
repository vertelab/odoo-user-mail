from odoo import models, fields, api, _
from odoo.exceptions import UserError
from cryptography.fernet import Fernet
from passlib.hash import sha512_crypt

import logging
_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    imap_password = fields.Char(string='IMAP Password', help='Encrypted IMAP password')

    imap_poll_enabled = fields.Boolean(
        string='Aktivera mail-pollning',
        default=False,
        help='Pollerar denna användares brevlåda via IMAP (cron).')
    last_imap_sync = fields.Datetime(
        string='Senaste IMAP-synk',
        help='Tidpunkt för senaste lyckade pollning (inkrementell hämtning).')

    # ── Min profil: exponera mail-fälten i preferences-dialogen ───────
    # base.view_users_form_simple_modif filtrerar sin arch mot dessa två
    # listor — utan överridningen renderas gruppen tom och flaggan kan
    # inte sparas. imap_password är Fernet-krypterad (aldrig klartext);
    # den är läsbar för ägaren men sätts alltid via wizarden.
    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + [
            'imap_password', 'imap_poll_enabled', 'last_imap_sync']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + [
            'imap_poll_enabled']

    def _get_encryption_key(self):
        param = self.env['ir.config_parameter'].sudo()
        key = param.get_param('user_mail_imap.encryption_key')
        if not key:
            key = Fernet.generate_key().decode()
            param.set_param('user_mail_imap.encryption_key', key)
        return key

    def _encrypt_imap_pw(self, password):
        if not password:
            return False
        f = Fernet(self._get_encryption_key().encode())
        return f.encrypt(password.encode()).decode()

    def _decrypt_imap_pw(self):
        if not self.imap_password:
            return None
        key = self._get_encryption_key()
        if not key:
            return None
        f = Fernet(key.encode())
        try:
            return f.decrypt(self.imap_password.encode()).decode()
        except Exception:
            return None

    # ── Verifiering mot Dovecot-hashen ────────────────────────────────

    def _verify_dovecot_password(self, password):
        """Verifiera ett lösenord mot användarens Dovecot-hash.

        Odoo- och mail-lösenordet är samma lösenord. Dovecot verifierar
        klienter mot `dovecot_password` (SHA512-CRYPT, enkelriktad), men
        IMAP-pollern måste ha klartexten — därför sparas en tvåvägskrypterad
        kopia i `imap_password`. Här bekräftar vi att det användaren skriver
        faktiskt är deras mail-lösenord innan kopian sparas.

        Returnerar True (matchar), False (matchar inte), None (kan inte
        verifiera — ingen eller trasig hash).
        """
        self.ensure_one()
        if not password:
            return False
        if not self.dovecot_password:
            return None
        try:
            return bool(sha512_crypt.verify(password, self.dovecot_password))
        except (ValueError, TypeError) as e:
            _logger.warning(
                'Mail-credentials: kunde inte verifiera lösenord mot '
                'dovecot_password för %s (trasig hash?): %s',
                self.login, e)
            return None

    def action_set_imap_password(self, password):
        """Sätt IMAP-lösenordet efter verifiering mot Dovecot-hashen.

        Sparar den tvåvägskrypterade kopian (`imap_password`) som pollern
        behöver. Klartexten sparas aldrig.
        """
        self.ensure_one()
        if not password:
            raise UserError(_('Ange ditt mail-lösenord.'))
        verdict = self._verify_dovecot_password(password)
        if verdict is False:
            raise UserError(
                _('Lösenordet stämmer inte med ditt mail-lösenord. '
                  'Prova igen.'))
        if verdict is None:
            _logger.info(
                'Mail-credentials: ingen dovecot_password för %s — '
                'IMAP-lösenordet sparas utan verifiering.', self.login)
        self.sudo().imap_password = self._encrypt_imap_pw(password)
        return True

    # ── Livscykel: Odoo-lösenordet är mail-lösenordet ──────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('password'):
                vals['imap_password'] = self._encrypt_imap_pw(vals['password'])
            if vals.get('imap_poll_enabled') and not vals.get('imap_password'):
                raise UserError(
                    _('Sätt ditt mail-lösenord innan du aktiverar '
                      'mail-pollning.'))
        return super().create(vals_list)

    def write(self, values):
        if values.get('password'):
            values['imap_password'] = self._encrypt_imap_pw(values['password'])
            _logger.info(
                'Mail-credentials: imap_password synkades från '
                'Odoo-lösenordet för %s (samma lösenord av design).',
                ', '.join(self.mapped('login')))
        # Poll-flaggan kräver ett lösenord — annars hamnar användaren i en
        # permanent felloop (pollern kastar var 5:e minut, för evigt).
        if values.get('imap_poll_enabled'):
            for user in self:
                effective = values.get('imap_password') or user.imap_password
                if not effective:
                    raise UserError(
                        _('Sätt ditt mail-lösenord innan du aktiverar '
                          'mail-pollning.'))
        return super().write(values)
