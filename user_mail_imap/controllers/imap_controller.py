from odoo import http
from odoo.exceptions import UserError
from odoo.http import request


class ImapController(http.Controller):

    @http.route('/imap/check', type='json', auth='user')
    def check_password(self):
        pw = request.env.user._decrypt_imap_pw()
        return {'has_password': bool(pw)}

    @http.route('/imap/set_password', type='json', auth='user')
    def set_password(self, password):
        # Verifiera mot dovecot_password innan kopian sparas -- samma vag
        # som Min profil anvander (action_set_imap_password). Utan detta
        # sparades ett felaktigt losenord tyst och felet syntes forst vid
        # nasta IMAP-anslutning (Authentication failed).
        if not password:
            return {'error': 'Password required'}
        try:
            request.env.user.action_set_imap_password(password)
        except UserError as e:
            return {'error': str(e)}
        return {'ok': True}

    @http.route('/imap/folders', type='json', auth='user')
    def folders(self):
        imap = request.env['user.mail.imap'].sudo()
        return imap.action_list_folders()

    @http.route('/imap/mails', type='json', auth='user')
    def mails(self, folder='INBOX', offset=0, limit=50):
        imap = request.env['user.mail.imap'].sudo()
        return imap.action_fetch_mails(folder, offset, limit)

    @http.route('/imap/search', type='json', auth='user')
    def search(self, folder='INBOX', query='', offset=0, limit=50):
        imap = request.env['user.mail.imap'].sudo()
        return imap.action_search_mails(folder, query, offset, limit)

    @http.route('/imap/mail', type='json', auth='user')
    def mail(self, folder, uid):
        imap = request.env['user.mail.imap'].sudo()
        return imap.action_fetch_mail(folder, uid)

    @http.route('/imap/send', type='json', auth='user')
    def send(self, to, subject, body, cc=''):
        imap = request.env['user.mail.imap'].sudo()
        imap.action_send_mail(to, subject, body, cc)
        return {'ok': True}

    @http.route('/imap/flag', type='json', auth='user')
    def flag(self, folder, uids, flag, value):
        imap = request.env['user.mail.imap'].sudo()
        imap.action_set_flag(folder, uids, flag, value)
        return {'ok': True}

    @http.route('/imap/sync', type='json', auth='user')
    def sync(self):
        """Force refresh — clear caches and return fresh data."""
        imap = request.env['user.mail.imap'].sudo()
        imap.action_clear_cache()
        return {'ok': True}

