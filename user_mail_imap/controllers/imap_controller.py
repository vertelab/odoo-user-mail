import json

from odoo import http
from odoo.exceptions import UserError, ValidationError
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

    @http.route('/imap/rule/create', type='json', auth='user')
    def rule_create(self, name, condition_kind, condition_text, action,
                    folder='', enforcement='server'):
        """Skapa en mailregel från ett meddelande.

        Ligger här och inte i user_mail_ai därför att dialogen ägs av
        user_mail_imap (den öppnas från meddelandevyn). Modellen finns bara
        om user_mail_ai är installerad — vi letar i stället för att importera,
        så klienten fungerar utan AI-modulen.

        Valideringen (Sieve-uttryckbarhet) körs av modellens constrains. Vi
        fångar den och skickar tillbaka texten, så dialogen kan visa felet
        utan att stängas.
        """
        if 'user_mail_ai.rule' not in request.env:
            raise UserError('Mailregler kräver modulen user_mail_ai.')
        action_config = {}
        if action == 'move_to_folder':
            if not folder:
                raise UserError('Välj en mapp att flytta till.')
            action_config['folder'] = folder
        try:
            rule = request.env['user_mail_ai.rule'].create({
                'user_id': request.env.user.id,
                'name': name,
                'condition_kind': condition_kind,
                'condition_text': condition_text,
                'action': action,
                'action_config': json.dumps(action_config),
                'enforcement': enforcement,
            })
        except ValidationError as e:
            # Dialogen visar texten; ett kastat fel hade stängt den och
            # användaren hade fått börja om från början.
            raise UserError(str(e))
        return {'ok': True, 'rule_id': rule.id}
