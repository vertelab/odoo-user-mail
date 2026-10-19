from odoo import models, api, fields, _
from odoo.exceptions import UserError
from email import policy
from email.parser import BytesParser
from email.message import EmailMessage
import email.utils
import hashlib
import imaplib
import smtplib
import time
import odoo.tools
import logging

import re

_logger = logging.getLogger(__name__)


def _safe_logout(conn):
    """Log out without throwing away the result of the operation.

    ``imaplib.logout()`` may answer something other than ``OK`` (e.g. when
    the server sends a leftover message body instead of the status line).
    That raises ``IMAP4.error``. Previously ``conn.logout()`` sat bare in
    ``finally``, so a broken LOGOUT response discarded a fully successful
    poll -- and the whole user poll was logged as ERROR every five minutes.

    Logging out is cleanup, not the result. It must never fail the job.
    """
    try:
        conn.logout()
    except Exception as e:
        _logger.warning('IMAP logout failed (ignored): %s', e)
        try:
            conn.shutdown()
        except Exception:
            pass

# Simple mail detail cache
_mail_cache = {}

# Matches an opening <a> tag that has an href but no target attribute yet.
# The lookahead requires href (so `<a name="anchor">` is left alone), skips
# pure fragment links (href="#..." / href='#...' — they must stay in the same
# document), and the negative lookahead preserves an existing target
# (case-insensitively, thanks to re.IGNORECASE). Both quote styles are
# accepted: mail HTML frequently uses single quotes.
_LINK_RE = re.compile(
    r'<a\s+(?=[^>]*\bhref=["\'](?!#))(?![^>]*\btarget=)([^>]*)>',
    re.IGNORECASE,
)


def _prepare_body_html(html):
    """Make links in a mail body open in a new window.

    Mail HTML is rendered inside an iframe. Without this, a link click would
    navigate the iframe itself: Odoo answers its own webclient with
    ``X-Frame-Options: DENY``, so the browser refuses to display the target.
    Opening in a new window keeps the mail client in place and sidesteps the
    framing restriction entirely.

    ``rel="noopener noreferrer"`` protects against the opened page reaching
    back through ``window.opener``.
    """
    if not html:
        return html

    def repl(match):
        return '<a %s target="_blank" rel="noopener noreferrer">' % match.group(1).rstrip()

    return _LINK_RE.sub(repl, html)


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
            _safe_logout(conn)

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
            _safe_logout(conn)

    def action_search_mails(self, folder='INBOX', query='', offset=0, limit=80):
        """Search the current folder, OKF-backed when available.

        Returns the same dict shape as ``action_fetch_mails``
        (``{'messages': [...], 'total': n}``).

        When ``ai.okf.concept`` is installed the query is resolved through
        OKF hybrid search over the user's personal archive (one indexed SQL
        query) and the hits are mapped back to mail rows via
        ``user_mail_ai.mail``. This replaces the old live IMAP ``SEARCH``,
        which scanned every message body (``TEXT``) on each call. Without
        the OKF model the method falls back to the IMAP ``SEARCH``
        implementation, so ``user_mail_imap`` stays standalone.
        """
        term = (query or '').strip()
        if not term:
            return {'messages': [], 'total': 0}
        if 'ai.okf.concept' in self.env:
            return self._search_mails_okf(folder, term, offset, limit)
        return self._search_mails_imap(folder, term, offset, limit)

    def _search_mails_okf(self, folder, term, offset=0, limit=80):
        """Resolve the query through OKF hybrid search (personal scope).

        The OKF concept stores only ``source_ref`` (= the mail's
        Message-ID); folder/uid live in ``user_mail_ai.mail``. Hits are
        joined back on ``message_id``, scoped to the current user and folder,
        and emitted in OKF relevance order. Hits with no matching ingested
        mail row are dropped, and ``total`` counts only resolved rows.

        ``semantic=False`` (2026-10-14) — this is an INTERACTIVE search box,
        so the query embedding is skipped. That embedding is a synchronous
        HTTP call to an external provider (timeout 20 s x 3 attempts, so up
        to 60 s when the provider hangs), which made the search feel broken.
        Swedish FTS (BM25) answers in milliseconds and is what "find the mail
        with the invoice" needs. Agent retrieval, where recall outweighs
        latency, keeps the default (``semantic=True``).

        ``offset`` is applied to the relevance-ordered result. OKF search has
        no native offset, so ``limit + offset`` hits are fetched and the
        window is sliced out — best-effort paging, matching the design's
        stated trade-off.
        """
        Concept = self.env['ai.okf.concept']
        if 'user_mail_ai.mail' not in self.env:
            # OKF present but the mail model is not: nothing to resolve.
            return {'messages': [], 'total': 0}
        Mail = self.env['user_mail_ai.mail']
        hits = Concept._okf_search(
            query=term, scope='personal', owner_id=self.env.user.id,
            limit=limit + max(0, offset), semantic=False)
        if not hits:
            return {'messages': [], 'total': 0}
        # Message-IDs in relevance order; source_ref is the concept's stored
        # Message-ID. Keep the order to emit rows ranked, not by UID.
        message_ids = []
        for concept in hits:
            message_id = (concept.source_ref or '').strip()
            if message_id and message_id not in message_ids:
                message_ids.append(message_id)
        if not message_ids:
            return {'messages': [], 'total': 0}
        mail_rows = Mail.search_read(
            [('user_id', '=', self.env.user.id),
             ('message_id', 'in', message_ids),
             ('source_folder', '=', folder)],
            ['message_id', 'source_uid', 'source_folder', 'subject',
             'from_email', 'from_name', 'received_at'])
        by_message_id = {row['message_id']: row for row in mail_rows}
        resolved = []
        for message_id in message_ids:
            row = by_message_id.get(message_id)
            if not row:
                # OKF hit without an ingested mail row: omit (never a broken
                # row), and it does not count toward the total.
                continue
            resolved.append(row)
        total = len(resolved)
        page = resolved[offset:offset + limit]
        messages = [self._okf_mail_row(row) for row in page]
        return {'messages': messages, 'total': total}

    @staticmethod
    def _okf_mail_row(row):
        """Map an ``user_mail_ai.mail`` row to a mail-list entry."""
        from_ = row.get('from_email') or ''
        if row.get('from_name') and from_:
            from_ = '%s <%s>' % (row['from_name'], from_)
        elif row.get('from_name'):
            from_ = row['from_name']
        received = row.get('received_at')
        return {
            'uid': row.get('source_uid') or 0,
            'seen': False,
            'flagged': False,
            'from_': from_,
            'subject': row.get('subject') or '(No subject)',
            'date': received.strftime('%a, %d %b %Y %H:%M:%S %z')
                    if hasattr(received, 'strftime') else str(received or ''),
            'message_id': row.get('message_id') or '',
        }

    def _search_mails_imap(self, folder, term, offset=0, limit=80):
        """Sök i en mapp med IMAP:s egna SEARCH-kommando (fallback).

        Söker server-side i avsändare, rubrik och text (FROM/SUBJECT/TEXT),
        så hela mappen täcks — inte bara de meddelanden som redan hämtats
        till listan. Returnerar samma dict-form som action_fetch_mails.

        IMAP:s ``OR`` tar exakt två söknycklar, så tre kriterier kräver
        nästling: ``OR OR FROM "q" SUBJECT "q" TEXT "q"`` läses som
        ``OR (OR (FROM q) (SUBJECT q)) (TEXT q)``.
        """
        # Escapa citattecken så att de inte bryter IMAP-strängen.
        escaped = term.replace('\\', '\\\\').replace('"', '\\"')
        criteria = 'OR OR FROM "%s" SUBJECT "%s" TEXT "%s"' % (
            escaped, escaped, escaped)

        conn = self._connect_imap()
        try:
            conn.select(folder)
            typ, data = conn.search(None, criteria)
            if typ != 'OK':
                return {'messages': [], 'total': 0}
            uids = data[0].split() if data and data[0] else []
            # Nyaste först: IMAP returnerar UID i stigande ordning.
            uids = sorted(uids, key=int, reverse=True)
            total = len(uids)
            page = uids[offset:offset + limit]
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
                'messages': messages,
                'total': total,
            }
        finally:
            _safe_logout(conn)

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
                'body_html': _prepare_body_html(body_html or body_text or '(No content)'),
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
            _safe_logout(conn)

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
            _safe_logout(conn)

    # ══════════════════════════════════════════════════════════════
    # Polling (cron, per-user) — mail-infrastruktur, ingen AI
    # ══════════════════════════════════════════════════════════════

    @api.model
    def action_poll_all(self):
        """Poll every user with imap_poll_enabled=True and a password.

        Körs av cron via user.mail.poll. Varje användare pollas med sin
        egen IMAP-identitet (with_user) och sina egna credentials. Ett fel
        för en användare blockerar aldrig övriga.

        En användare utan `imap_password` hoppas över tyst: ytan nekar
        `imap_poll_enabled` utan lösenord, så ett saknat lösenord är ett
        normalt tillstånd — inte ett fel att logga var 5:e minut.
        """
        users = self.env['res.users'].search(
            [('imap_poll_enabled', '=', True)])
        total = 0
        for user in users:
            if not user.imap_password:
                _logger.info(
                    'Mail poll: hoppar över %s — inget IMAP-lösenord satt.',
                    user.login)
                continue
            try:
                total += self.with_user(user.id).action_poll_user()
            except Exception as e:
                _logger.error(
                    'Mail poll failed for user %s (%s): %s',
                    user.login, user.id, e)
        return total

    def action_poll_user(self):
        """Poll ONE user's INBOX (env.user = target user).

        Readonly-säker: använder BODY.PEEK så att \\Seen aldrig sätts och
        inga flaggor/mappar ändras. Hämtar mail sedan last_imap_sync,
        normaliserar, deduplicerar via Message-ID, anropar
        _on_new_messages() per batch och uppdaterar last_imap_sync.
        """
        user = self.env.user
        since = user.last_imap_sync
        conn = self._connect_imap()
        try:
            conn.select('INBOX')
            if since:
                date_str = since.strftime('%d-%b-%Y')
                typ, data = conn.search(None, '(SINCE %s)' % date_str)
            else:
                typ, data = conn.search(None, 'ALL')
            if typ != 'OK':
                return 0
            uids = data[0].split() if data and data[0] else []
            processed = set(self._get_processed_message_ids(user.id))
            messages = []
            for uid in uids:
                typ2, msg_data = conn.fetch(uid, '(BODY.PEEK[])')
                if (typ2 != 'OK' or not msg_data
                        or not isinstance(msg_data[0], tuple)):
                    continue
                _flags_raw, raw = msg_data[0]
                try:
                    norm = self._normalize_message(
                        raw, folder='INBOX', uid=int(uid))
                except Exception as e:
                    _logger.warning(
                        'Normalize failed for %s uid=%s: %s',
                        user.login, uid, e)
                    continue
                if not norm:
                    continue
                key = norm.get('dedup_key')
                if key and key in processed:
                    continue
                if key:
                    processed.add(key)
                messages.append(norm)
            if messages:
                self._on_new_messages(messages)
                self._record_processed(user.id, messages)
            user.write({'last_imap_sync': fields.Datetime.now()})
            return len(messages)
        finally:
            _safe_logout(conn)

    def _get_processed_message_ids(self, user_id):
        """Alla redan processade dedup-nycklar för användaren."""
        return self.env['user.mail.processed'].sudo().search(
            [('user_id', '=', user_id)]).mapped('message_id')

    def _record_processed(self, user_id, messages):
        """Beständig dedup: spara Message-ID/dedup-nyckel per användare."""
        vals = []
        for m in messages:
            key = m.get('dedup_key')
            if not key:
                continue
            vals.append({'user_id': user_id, 'message_id': key})
        if vals:
            self.env['user.mail.processed'].sudo().create(vals)

    @staticmethod
    def _dedup_key(norm):
        """Message-ID när det finns; annars hash av (from, subject, date)."""
        mid = (norm.get('message_id') or '').strip()
        if mid:
            return mid
        raw = '%s|%s|%s' % (
            norm.get('from_', ''),
            norm.get('subject', ''),
            norm.get('date', ''),
        )
        return 'h:' + hashlib.md5(
            raw.encode('utf-8', 'ignore')).hexdigest()

    def _normalize_message(self, raw_bytes, folder='INBOX', uid=None):
        """Parsa en rå RFC822-message till den normaliserade dict-formen.

        Returns dict: message_id, subject, from_, to_, date, body_text,
        body_html, attachments (list of {filename, content_type}), folder,
        raw (bytes) och dedup_key.
        """
        msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)
        body_text = ''
        body_html = ''
        attachments = []
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                fn = part.get_filename()
                if fn:
                    attachments.append({'filename': fn, 'content_type': ct})
                elif ct == 'text/plain' and not body_text:
                    body_text = part.get_content() or ''
                elif ct == 'text/html' and not body_html:
                    body_html = part.get_content() or ''
        else:
            ct = msg.get_content_type()
            if ct == 'text/html':
                body_html = msg.get_content() or ''
            else:
                body_text = msg.get_content() or ''
        norm = {
            'uid': uid,
            'message_id': str(msg.get('Message-ID', '')).strip(),
            'subject': str(msg.get('Subject', '')),
            'from_': str(msg.get('From', '')),
            'to_': str(msg.get('To', '')),
            'date': str(msg.get('Date', '')),
            'body_text': body_text,
            'body_html': body_html,
            'attachments': attachments,
            'folder': folder,
            'raw': raw_bytes,
        }
        norm['dedup_key'] = self._dedup_key(norm)
        return norm


    # ══════════════════════════════════════════════════════════════
    # Drafts & mappar (Skiva 2 — utåtgående, HITL-gat)
    # ══════════════════════════════════════════════════════════════

    def _drafts_folder(self):
        """Drafts-mapp: LIST-detektering (Drafts/Utkast) med konfig-fallback."""
        param = self.env['ir.config_parameter'].sudo().get_param(
            'user_mail_imap.drafts_folder', '')
        if param:
            return param
        try:
            conn = self._connect_imap()
            try:
                for item in conn.list()[1]:
                    decoded = item.decode('utf-8', 'ignore')
                    m = re.search(r'\s"\S+"\s"([^"]+)"', decoded)
                    name = m.group(1) if m else decoded.rsplit(' ', 1)[-1]
                    if name.lower() in ('drafts', 'utkast'):
                        return name
            finally:
                _safe_logout(conn)
        except Exception as e:
            _logger.warning('Drafts folder detection failed: %s', e)
        return 'Drafts'

    def action_append_draft(self, to, subject, body, in_reply_to=None,
                            cc='', folder=None):
        """APPEND:a ett utkast till användarens Drafts-mapp (IMAP).

        Körs i användarens kontext (env.user). Returnerar UID (via
        UIDPLUS/appenduid eller sök på Message-ID).
        """
        user = self.env.user
        conn = self._connect_imap()
        try:
            folder = folder or self._drafts_folder()
            msg = EmailMessage()
            msg['From'] = user.postfix_mail or ''
            msg['To'] = to
            if cc:
                msg['Cc'] = cc
            msg['Subject'] = subject
            if in_reply_to:
                msg['In-Reply-To'] = in_reply_to
                msg['References'] = in_reply_to
            msg['Date'] = email.utils.formatdate(localtime=True)
            mid = '<%s@vertel>' % hashlib.md5(
                ('%s%s%s' % (to, subject, fields.Datetime.now())).encode()
            ).hexdigest()
            msg['Message-ID'] = mid
            msg.set_content(body)
            typ, data = conn.append(
                folder, '\\Draft', imaplib.Time2Internaldate(time.time()),
                msg.as_bytes())
            # UIDPLUS: appenduid returnerar UID
            uid = None
            if data and data[0]:
                m = re.search(rb'APPENDUID \d+ (\d+)', data[0])
                if m:
                    uid = int(m.group(1))
            if uid is None:
                # Fallback: sök på Message-ID
                try:
                    conn.select(folder)
                    typ2, sdata = conn.search(None, '(HEADER Message-ID "%s")' % mid)
                    if typ2 == 'OK' and sdata and sdata[0]:
                        uid = int(sdata[0].split()[-1])
                except Exception:
                    pass
            return {'folder': folder, 'uid': uid, 'message_id': mid}
        finally:
            _safe_logout(conn)

    def action_move(self, folder, uids, to_folder):
        """Flytta mail mellan mappar (UID MOVE, fallback COPY+DEL+EXPUNGE)."""
        conn = self._connect_imap()
        try:
            conn.select(folder)
            uid_list = ','.join(str(u) for u in uids)
            typ, _data = conn.uid('MOVE', uid_list, to_folder)
            if typ != 'OK':
                # Fallback: COPY + \Deleted + EXPUNGE
                conn.uid('COPY', uid_list, to_folder)
                conn.uid('STORE', uid_list, '+FLAGS', '\\Deleted')
                conn.expunge()
            return True
        finally:
            _safe_logout(conn)

    def action_ensure_folder(self, folder):
        """Skapa mapp om den inte finns (best-effort)."""
        conn = self._connect_imap()
        try:
            try:
                conn.create(folder)
                return True
            except Exception:
                return False
        finally:
            _safe_logout(conn)

    def action_fetch_draft_raw(self, folder, uid):
        """Hämta råa innehållet i ett utkast (för HITL-skick)."""
        conn = self._connect_imap()
        try:
            conn.select(folder)
            typ, data = conn.fetch(str(uid).encode(), '(BODY.PEEK[])')
            if typ == 'OK' and data and isinstance(data[0], tuple):
                return data[0][1]
            return None
        finally:
            _safe_logout(conn)

    def _on_new_messages(self, messages):
        """Hook — anropas per användarbatch efter en lyckad pollning.

        Bryggmoduler (t.ex. user_mail_ai) ärver user.mail.imap och
        överlagrar denna för att konsumera de normaliserade mailet.
        Här: no-op.
        """
        return len(messages)
