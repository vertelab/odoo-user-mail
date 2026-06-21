from odoo import models, api, _
from odoo.exceptions import UserError
from email import policy
from email.parser import BytesParser
from email.message import EmailMessage
import imaplib
import smtplib
import odoo.tools
import logging

import re

_logger = logging.getLogger(__name__)

# Simple mail detail cache
_mail_cache = {}


class ImapServer(models.AbstractModel):
    _name = 'user.mail.imap'
    _description = 'IMAP Mail Operations'

    def _get_config(self, key, default=None):
        return odoo.tools.config.get(key, default)

    def _decrypt_password(self):
        user = self.env.user
        if not user.imap_password:
            return None
        return user._decrypt_imap_pw()

    def _connect_imap(self):
        password = self._decrypt_password()
        if not password:
            raise UserError(_("No IMAP password configured. Use user settings to set it."))
        host = self._get_config('imap_host', 'localhost')
        port = int(self._get_config('imap_port', 993))
        user = self.env.user.postfix_mail
        if not user:
            raise UserError(_("No postfix mail configured for this user."))
        conn = imaplib.IMAP4_SSL(host, port)
        conn.login(user, password)
        return conn

    def action_list_folders(self):
        conn = self._connect_imap()
        try:
            result = []
            for item in conn.list()[1]:
                decoded = item.decode('utf-8')
                _logger.info('IMAP FOLDER RAW: %s', decoded)
                # Format: '(\HasNoChildren) "." "INBOX.Sent"'
                # Parse flags, delimiter, and name properly
                flags_end = decoded.index(')')
                flags = decoded[1:flags_end].split()
                rest = decoded[flags_end + 2:].strip()
                # Use regex to extract quoted delimiter and quoted name
                m = re.match(r'"(.*?)"\s+"(.+)"', rest)
                if m:
                    delim = m.group(1)
                    name = m.group(2)
                else:
                    # Fallback: delimiter might be unquoted (e.g. just a dot)
                    # Format: '. "folder"' or '"\\." "folder"'
                    m2 = re.match(r'(\S+)\s+"(.+)"', rest)
                    if m2:
                        delim = m2.group(1).strip('"')
                        name = m2.group(2)
                    else:
                        parts = rest.split(' ', 1)
                        delim = parts[0].strip('"') if parts[0] != 'NIL' else '/'
                        name = parts[1].strip('" ') if len(parts) > 1 else ''
                _logger.info('IMAP FOLDER PARSED: name=%r delim=%r (%d chars) hex=%s', name, delim, len(delim), delim.encode().hex())
                result.append({
                    'name': name,
                    'delimiter': delim,
                    'flags': flags,
                })
            return result
        finally:
            conn.logout()

    def action_fetch_mails(self, folder='INBOX', offset=0, limit=80):
        conn = self._connect_imap()
        try:
            conn.select(folder)
            _, data = conn.search(None, 'ALL')
            uids = data[0].split()
            total = len(uids)
            page = uids[max(0, total - offset - limit):total - offset] if uids else []
            messages = []
            for uid in page:
                _, msg_data = conn.fetch(uid, '(FLAGS BODY.PEEK[HEADER])')
                raw = msg_data[0]
                if not isinstance(raw, tuple):
                    continue
                flags, header_raw = raw
                msg = BytesParser(policy=policy.default).parsebytes(header_raw)
                messages.append({
                    'uid': int(uid),
                    'seen': b'\\Seen' in flags,
                    'flagged': b'\\Flagged' in flags,
                    'from_': str(msg.get('From', '')),
                    'subject': str(msg.get('Subject', '(No subject)')),
                    'date': str(msg.get('Date', '')),
                    'message_id': str(msg.get('Message-ID', '')),
                })
            return {
                'messages': list(reversed(messages)),
                'total': total,
            }
        finally:
            conn.logout()

    def action_fetch_mail(self, folder, uid):
        cache_key = f"{self.env.user.id}:{folder}:{uid}"
        if cache_key in _mail_cache:
            return _mail_cache[cache_key]

        conn = self._connect_imap()
        try:
            conn.select(folder)
            _, data = conn.fetch(str(uid).encode(), '(RFC822 FLAGS)')
            raw = data[0]
            if not isinstance(raw, tuple):
                return None
            flags, raw_email = raw
            msg = BytesParser(policy=policy.default).parsebytes(raw_email)
            body_html = ''
            body_text = ''
            attachments = []
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct == 'text/html' and not body_html:
                        body_html = part.get_content()
                    elif ct == 'text/plain' and not body_text:
                        body_text = part.get_content()
                    elif part.get_filename():
                        attachments.append({
                            'filename': part.get_filename(),
                            'content_type': ct,
                        })
            else:
                body_html = msg.get_content()
            result = {
                'uid': int(uid),
                'seen': b'\\Seen' in flags,
                'from_': str(msg.get('From', '')),
                'to_': str(msg.get('To', '')),
                'cc_': str(msg.get('Cc', '')),
                'subject': str(msg.get('Subject', '(No subject)')),
                'date': str(msg.get('Date', '')),
                'body_html': body_html or body_text or '(No content)',
                'attachments': attachments,
            }
            _mail_cache[cache_key] = result
            # Limit cache size
            if len(_mail_cache) > 500:
                keys = list(_mail_cache.keys())
                for k in keys[:100]:
                    del _mail_cache[k]
            return result
        finally:
            conn.logout()

    def action_clear_cache(self):
        """Clear the mail detail cache."""
        _mail_cache.clear()
        return {'ok': True}

    def action_send_mail(self, to, subject, body, cc=''):
        password = self._decrypt_password()
        if not password:
            raise UserError(_("No IMAP password configured."))
        host = self._get_config('smtp_server', 'localhost')
        port = int(self._get_config('smtp_port', 587))
        encryption = self._get_config('smtp_encryption', 'starttls')
        user = self.env.user.postfix_mail
        conn = smtplib.SMTP(host, port)
        if encryption == 'starttls':
            conn.starttls()
        elif encryption == 'ssl':
            conn = smtplib.SMTP_SSL(host, port)
        conn.login(user, password)
        try:
            msg = EmailMessage()
            msg['From'] = user
            msg['To'] = to
            if cc:
                msg['Cc'] = cc
            msg['Subject'] = subject
            msg.set_content(body)
            conn.send_message(msg)
        finally:
            conn.quit()

    def action_set_flag(self, folder, uids, flag, value):
        conn = self._connect_imap()
        try:
            conn.select(folder)
            uid_list = ','.join(str(u) for u in uids)
            cmd = '+FLAGS' if value else '-FLAGS'
            imap_flag = '\\Seen' if flag == 'seen' else '\\Flagged'
            conn.uid('STORE', uid_list, cmd, imap_flag)
        finally:
            conn.logout()
