from odoo import models, fields


class ImapPasswordWizard(models.TransientModel):
    _name = 'user.mail.imap.password.wizard'
    _description = 'Set IMAP Password'

    password = fields.Char(string='Mail-lösenord', required=True,
                           password=True)

    def action_save(self):
        # Verifierar mot dovecot_password och sparar Fernet-kopian.
        # Klartexten lämnar aldrig wizarden.
        self.env.user.action_set_imap_password(self.password)
        return {'type': 'ir.actions.act_window_close'}
