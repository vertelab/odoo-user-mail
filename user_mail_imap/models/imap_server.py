from odoo import models, api, fields, _
from odoo.exceptions import UserError
from email import policy
from email.parser import BytesParser
from email.message import EmailMessage
import email.utils
import hashlib
import json
import imaplib
import smtplib
import time
import odoo.tools
import logging

import re

_logger = logging.getLogger(__name__)

# IMAP-kommandon har en längdgräns (RFC 3501 föreslår 1000 tecken för
# kommandoraden; Dovecot avvisar längre med "BAD Too long argument").
# En UID-lista på 11 000 poster blir ~60 000 tecken. Dela därför varje
# UID-baserad operation i bitar -- 200 UID:n ryms bekvämt inom gränsen
# även med sexsiffriga UID:n.
UID_BATCH_SIZE = 200


def _uid_batches(uids, size=UID_BATCH_SIZE):
    """Dela en UID-lista i bitar som ryms i ett IMAP-kommando."""
    uids = list(uids)
    for i in range(0, len(uids), size):
        yield uids[i:i + size]


def _quote_mailbox(folder):
    """Quote a mailbox name for an IMAP command when it needs it.

    ``imaplib`` does NOT quote arguments -- ``_command()`` appends each
    argument raw (``data + b' ' + arg``). A folder name containing a space
    therefore reaches Dovecot as *two* arguments:

        SELECT INBOX.Linkedin mm
        -> NO Mailbox doesn't exist: INBOX.Linkedin

    The trailing `` mm`` is silently dropped by the server, so the folder
    looks empty instead of failing loudly. Folders without spaces
    (``INBOX``, ``INBOX.Teamweb``) worked, which is why only some folders
    appeared broken.

    RFC 3501 allows either an atom or a quoted string. Quote whenever the
    name contains a space, a quote, a backslash or a control character --
    and also when it is empty. Backslash and double quote are escaped.
    """
    if not folder:
        return '""'
    if not any(c in folder for c in ' "\\') and folder.isprintable():
        return folder
    escaped = folder.replace('\\', '\\\\').replace('"', '\\"')
    return '"%s"' % escaped


def _select_folder(conn, folder):
    """SELECT a folder and fail loudly when the server refuses.

    ``imaplib.select()`` returns ``(typ, data)`` and resets ``state`` to
    ``AUTH`` on anything but ``OK``. The old code discarded the return
    value and went straight on to ``SEARCH``/``FETCH``, which then died
    with the opaque

        imaplib.IMAP4.error: command SEARCH illegal in state AUTH,
        only allowed in states SELECTED

    The user saw an empty folder instead of an error: the exception was
    swallowed by the controller and the list rendered with zero rows.
    That made a refused SELECT look like "all my mail is gone".

    Raising ``UserError`` here turns the same condition into a message
    the user can act on, and names the folder that failed.
    """
    typ, data = conn.select(_quote_mailbox(folder))
    if typ != 'OK':
        detail = ''
        if data and data[0]:
            raw = data[0]
            if isinstance(raw, bytes):
                raw = raw.decode('utf-8', 'ignore')
            detail = str(raw).strip()
        _logger.warning(
            'IMAP SELECT refused for %r: %s %s', folder, typ, detail)
        raise UserError(_(
            "Kunde inte öppna mappen '%(folder)s' på IMAP-servern "
            "(%(typ)s%(detail)s). Mappen kan vara otillgänglig, sakna "
            "lästrätt eller ha bytt namn.",
        ) % {
            'folder': folder,
            'typ': typ,
            'detail': (': ' + detail) if detail else '',
        })
    return data


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
        # Räknas per poll och rapporteras sammanfattat (se
        # `_report_logout_failures`). En kvarglömd meddelandekropp i
        # LOGOUT-svaret är en känd, ofarlig avvikelse: 55 separata
        # varningar per dag gör loggen oläsbar och döljer verkliga fel.
        _LOGOUT_FAILURES.append(str(e)[:160])
        try:
            conn.shutdown()
        except Exception:
            pass


def _report_logout_failures(user_login=None):
    """Logga LOGOUT-fel sammanfattat och töm räknaren.

    Ett nytt, annorlunda felmeddelande loggas separat — annars drunknar en
    verklig avvikelse i den kända. Tyst när inget fel inträffat.
    """
    if not _LOGOUT_FAILURES:
        return
    counts = {}
    for msg in _LOGOUT_FAILURES:
        counts[msg] = counts.get(msg, 0) + 1
    del _LOGOUT_FAILURES[:]
    for msg, n in counts.items():
        _logger.info(
            'IMAP logout failed (ignored) x%d for %s: %s',
            n, user_login or '?', msg)


# LOGOUT-fel ackumuleras per poll (se `_safe_logout`).
_LOGOUT_FAILURES = []

# Maildetalj-cache: cache_key -> (monotonic_timestamp, result).
# Tidsstämpeln gör att poster kan rensas även när inga nya läggs till —
# en storleksgräns ensam håller dem kvar så länge cachen inte fylls.
_mail_cache = {}
_MAIL_CACHE_TTL = 900  # sekunder

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


def _purge_mail_cache(ttl=None):
    """Ta bort cache-poster äldre än TTL.

    Körs vid varje läsning, inte bara vid insättning: en cache som bara
    töms när den passerar ett antal poster håller sina poster kvar så
    länge ingen ny post läggs till — och `body_html` för 500 mail är
    inte trivialt.
    """
    ttl = _MAIL_CACHE_TTL if ttl is None else ttl
    now = time.monotonic()
    stale = [k for k, (ts, _r) in _mail_cache.items() if now - ts > ttl]
    for k in stale:
        _mail_cache.pop(k, None)


def _page_cache_key(user_id, folder, offset, limit):
    """Cache-nyckel för en mappsida.

    Prefixet `page:` skiljer sid-poster från `action_fetch_mail`s
    `'{uid}:{folder}:{uid}'`. `offset` och `limit` MÅSTE ingå: annars
    serveras sida 1 för sida 2.
    """
    return 'page:%d:%s:%d:%d' % (user_id, folder, offset, limit)


def _invalidate_folder_cache(user_id, folder):
    """Ta bort alla cachade sidor för en användares mapp.

    Anropas när mappen ändras via applikationen (flaggbyte, flytt, nytt
    mail via pollern) — annars visar listvyn gammalt innehåll tills TTL
    går ut. Prefix-matchning räcker: antalet sidor per mapp är litet.
    """
    prefix = 'page:%d:%s:' % (user_id, folder)
    for key in [k for k in _mail_cache if k.startswith(prefix)]:
        _mail_cache.pop(key, None)


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
                # Hoppa över mappar som inte går att välja. Dovecot
                # exponerar sina interna noder i LIST men SELECT svarar NO,
                # och klienten försökte hämta dem — vilket gav aterkommande
                # "Kunde inte öppna mappen"-fel i UI:t.
                #
                # Två fall behövs: `dovecot` bär flaggan \Noselect, medan
                # `dovecot.sieve` INTE gör det (den rapporteras som en helt
                # vanlig \HasNoChildren-mapp och svarar SERVERBUG på SELECT).
                # Namnprefixet `dovecot` fångar därför den senare.
                if '\\Noselect' in flags:
                    continue
                if name == 'dovecot' or name.startswith('dovecot.'):
                    continue
                result.append({
                    'name': name,
                    'delimiter': delim,
                    'flags': flags,
                })
            return result
        finally:
            _safe_logout(conn)

    # RFC 6154 special-use → den mapp verktygsraden ska flytta till.
    # Arkivera har ingen standardflagga; \Archive förekommer men Dovecot
    # sätter den inte här, så den faller tillbaka på namnet "Archives".
    _SPECIAL_USE = {
        'trash': '\\Trash',
        'junk': '\\Junk',
        'archive': '\\Archive',
    }

    def action_special_folders(self):
        """Mapparna bakom Arkivera / Skräppost / Ta bort.

        Slås upp via RFC 6154-flaggor i stället för att hårdkoda namn:
        mappnamnen är lokaliserade ("Papperskorg" på svenska) och varierar
        mellan servrar. Hårdkodade namn ger en flytt till en mapp som inte
        finns — och då tappas mailet tyst.

        Arkivera saknar standardflagga. Finns ingen \\Archive letas namnet
        "Archives" (Dovecot:s vanligaste), annars utelämnas nyckeln och
        UI:t döljer knappen hellre än att gissa.
        """
        folders = self.action_list_folders()
        by_flag = {}
        for f in folders:
            for flag in f['flags']:
                for key, wanted in self._SPECIAL_USE.items():
                    if flag.lower() == wanted.lower():
                        by_flag.setdefault(key, f['name'])

        if 'archive' not in by_flag:
            for f in folders:
                if f['name'].lower() in ('archives', 'archive'):
                    by_flag['archive'] = f['name']
                    break

        return by_flag

    def action_fetch_mails(self, folder='INBOX', offset=0, limit=80):
        """Hämta en sida av en mapp — batchat och cacheat.

        Hämtningen görs med ETT `FETCH` per batch i stället för ett per
        meddelande: 80 separata rundturer mot en IMAP-server med ~10 ms RTT
        är ~0,8 s bara i tur-och-retur. Batchen delas av `_uid_batches()`
        så kommandoraden aldrig blir för lång (Dovecot svarar
        `BAD ... Too long argument` över ~1000 tecken).

        Ordningen är nyaste först och garanteras explicit: IMAP lovar inte
        att FETCH-svaren kommer i den ordning UID:na efterfrågades, så
        svaren samlas i en dict och emitteras i `page`-ordningen.

        Resultatet cachas per (användare, mapp, offset, limit) — ett
        mappbyte fram och tillbaka ska inte göra om IMAP-arbetet.
        """
        cache_key = _page_cache_key(self.env.user.id, folder, offset, limit)
        _purge_mail_cache()
        hit = _mail_cache.get(cache_key)
        if hit is not None:
            return hit[1]

        conn = self._connect_imap()
        try:
            _select_folder(conn, folder)
            # `conn.search()` skickar `SEARCH ALL`, som returnerar
            # SEKVENSNUMMER (1, 2, 3 …) — inte UID:n. Koden skickade dem
            # sedan som `UID FETCH`, vilket bara fungerar i mappar där UID
            # råkar sammanfalla med sekvensnumret (dvs. mappar som aldrig
            # komprimerats). I INBOX var första sekvensnumret 1 men första
            # UID 236543: `UID FETCH 1..10875` träffade ingenting och
            # Dovecot svarade `OK Fetch completed` med NOLL rader. Resultatet
            # blev en tom mapp utan ett enda felmeddelande.
            # `conn.uid('SEARCH', None, 'ALL')` ger de riktiga UID:na.
            typ, data = conn.uid('SEARCH', None, 'ALL')
            if typ != 'OK':
                # Tidigare kastades returvärdet: ett NEKAT SEARCH gav
                # `data = [b'']` -> noll UID:n -> en tom mapp som såg ut
                # som en tom brevlåda. Säg det i stället.
                _logger.warning(
                    'IMAP SEARCH refused for %r: %s %r', folder, typ, data)
                raise UserError(_(
                    "Kunde inte lista meddelanden i mappen '%(folder)s' "
                    "(%(typ)s).",
                ) % {'folder': folder, 'typ': typ})
            uids = data[0].split() if data and data[0] else []
            total = len(uids)
            page = uids[max(0, total - offset - limit):total - offset] if uids else []
            # Nyaste först: IMAP returnerar UID i stigande ordning.
            page = sorted(page, key=int, reverse=True)

            by_uid = {}
            for batch in _uid_batches(page):
                uid_set = ','.join(
                    u.decode() if isinstance(u, bytes) else str(u)
                    for u in batch)
                typ, msg_data = conn.uid(
                    'FETCH', uid_set, '(FLAGS BODY.PEEK[HEADER])')
                if typ != 'OK':
                    # Samma tysta väg som SEARCH ovan: ett nekat FETCH
                    # hoppades över utan ett ord, och sidan renderades tom.
                    _logger.warning(
                        'IMAP FETCH refused for %r uids=%s: %s %r',
                        folder, uid_set[:120], typ, msg_data)
                    continue
                if msg_data and all(i is None for i in msg_data):
                    # imaplib lägger serverns NO/BAD i untagged_responses och
                    # returnerar [None] som data. Det är den verkliga orsaken
                    # när en mapp med tusentals mail ger noll träffar.
                    _logger.warning(
                        'IMAP FETCH returned [None] for %r uids=%s; '
                        'untagged=%r',
                        folder, uid_set[:120],
                        {k: v for k, v in conn.untagged_responses.items()
                         if k not in ('EXISTS', 'FLAGS', 'UIDVALIDITY',
                                      'PERMANENTFLAGS', 'RECENT')})
                for item in msg_data or []:
                    if not isinstance(item, tuple):
                        continue
                    meta, header_raw = item[0], item[1]
                    if isinstance(meta, bytes):
                        meta = meta.decode('utf-8', 'ignore')
                    m = re.search(r'UID\s+(\d+)', meta or '')
                    if not m:
                        continue
                    uid = int(m.group(1))
                    flags = meta.encode() if isinstance(meta, str) else meta
                    try:
                        msg = BytesParser(
                            policy=policy.default).parsebytes(header_raw)
                    except Exception as e:
                        _logger.warning(
                            'Header parse failed uid=%s: %s: %s',
                            uid, type(e).__name__, e)
                        continue
                    by_uid[uid] = {
                        'uid': uid,
                        'seen': b'\\Seen' in flags,
                        'flagged': b'\\Flagged' in flags,
                        'from_': str(msg.get('From', '')),
                        'subject': str(msg.get('Subject', '(No subject)')),
                        'date': str(msg.get('Date', '')),
                        'message_id': str(msg.get('Message-ID', '')),
                    }

            # Emittera i page-ordningen. Ett UID servern inte svarade på
            # hoppas över — resten behåller sin inbördes ordning.
            messages = []
            for uid in page:
                entry = by_uid.get(int(uid))
                if entry is not None:
                    messages.append(entry)

            result = {'messages': messages, 'total': total}
            # Cacha EFTER lyckad hämtning — ett fel ska aldrig cachas.
            _mail_cache[cache_key] = (time.monotonic(), result)
            if len(_mail_cache) > 500:
                for k in list(_mail_cache.keys())[:100]:
                    del _mail_cache[k]
            return result
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
            _select_folder(conn, folder)
            typ, data = conn.uid('SEARCH', None, criteria)
            if typ != 'OK':
                return {'messages': [], 'total': 0}
            uids = data[0].split() if data and data[0] else []
            # Nyaste först: IMAP returnerar UID i stigande ordning.
            uids = sorted(uids, key=int, reverse=True)
            total = len(uids)
            page = uids[offset:offset + limit]
            messages = []
            for uid in page:
                # `conn.fetch()` tolkar argumentet som SEKVENSNUMMER.
                # Här är `uid` ett riktigt UID — fel kommando gav `[None]`
                # och tysta hopp. `conn.uid('FETCH', ...)` är rätt.
                typ_f, msg_data = conn.uid(
                    'FETCH', uid.decode() if isinstance(uid, bytes)
                    else str(uid), '(FLAGS BODY.PEEK[HEADER])')
                if typ_f != 'OK' or not msg_data or msg_data[0] is None:
                    continue
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
        _purge_mail_cache()
        hit = _mail_cache.get(cache_key)
        if hit is not None:
            return hit[1]

        conn = self._connect_imap()
        try:
            _select_folder(conn, folder)
            # UID, inte sekvensnummer: `conn.fetch()` tolkar argumentet
            # som sekvensnummer och gav `[None]` -> `data[0]` kastade
            # IndexError. `conn.uid('FETCH', ...)` är rätt kommando.
            typ_f, data = conn.uid(
                'FETCH', str(uid), '(RFC822 FLAGS)')
            if typ_f != 'OK' or not data or data[0] is None:
                return None
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
            _mail_cache[cache_key] = (time.monotonic(), result)
            # Limit cache size (TTL-purge sker vid varje läsning).
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
            _select_folder(conn, folder)
            cmd = '+FLAGS' if value else '-FLAGS'
            imap_flag = '\\Seen' if flag == 'seen' else '\\Flagged'
            for batch in _uid_batches(uids):
                uid_list = ','.join(str(u) for u in batch)
                conn.uid('STORE', uid_list, cmd, imap_flag)
        finally:
            _safe_logout(conn)
        # Flaggbytet ska synas i listvyn direkt, inte efter TTL.
        _invalidate_folder_cache(self.env.user.id, folder)

    # ══════════════════════════════════════════════════════════════
    # Polling (cron, per-user) — mail-infrastruktur, ingen AI
    # ══════════════════════════════════════════════════════════════

    # ── Budget, chunkning och progress ────────────────────────────

    def _poll_param(self, key, default):
        """Läs en poll-inställning ur ir.config_parameter (sträng → typ)."""
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'user_mail_imap.%s' % key, default)
        try:
            return type(default)(raw)
        except (TypeError, ValueError):
            return default

    def _report_progress(self, done, remaining):
        """Rapportera framsteg till Odoo 18:s cron-progress-API.

        `ir_cron._run_job()` committar progress-raden FÖRE varje anrop och
        schemalägger om direkt (`PARTIALLY_DONE`) så länge `remaining > 0`.
        Utanför cron (manuell trigger, tester) saknas `ir_cron_progress_id`
        i context — då är anropet en tyst no-op.
        """
        if not self.env.context.get('ir_cron_progress_id'):
            return
        # `_notify_progress` bor på ir.cron, inte på user.mail.imap.
        # Anropet låg tidigare på self och kastade AttributeError -- i slutet
        # av action_poll_all(), inom samma transaktion som cursor-skrivningen.
        # En lyckad pollning rullades därför tillbaka och last_imap_uid
        # skrevs aldrig.
        #
        # Progressrapportering är observability, inte affärslogik: går den
        # sönder ska pollningen ändå spara sitt resultat.
        try:
            self.env['ir.cron']._notify_progress(
                done=done, remaining=remaining)
        except Exception as e:
            _logger.warning(
                'IMAP poll: progress-rapportering misslyckades (ignored): %r', e)

    @api.model
    def action_poll_all(self):
        """Polla alla användare med imap_poll_enabled=True och lösenord.

        Körs av cron via user.mail.poll. Arbetet är **chunkat och
        budgeterat**: en körning tar aldrig längre tid än
        `poll_budget_seconds`, och det som återstår rapporteras via
        progress-API:t så att cron schemalägger om direkt.

        En användare utan `imap_password` hoppas över tyst: ytan nekar
        `imap_poll_enabled` utan lösenord, så ett saknat lösenord är ett
        normalt tillstånd — inte ett fel att logga var 5:e minut.
        """
        budget = self._poll_param('poll_budget_seconds', 30)
        deadline = time.monotonic() + budget
        users = self.env['res.users'].search(
            [('imap_poll_enabled', '=', True)])
        total = 0
        pending = list(users)
        while pending:
            if time.monotonic() >= deadline:
                # Budgeten är slut: räkna resten som återstående arbete.
                self._report_progress(total, len(pending))
                return total
            user = pending.pop(0)
            if not user.imap_password:
                _logger.info(
                    'Mail poll: hoppar över %s — inget IMAP-lösenord satt.',
                    user.login)
                continue
            try:
                new, failed = self.with_user(user.id).action_poll_user(
                    deadline=deadline)
                total += new
                if failed:
                    # Enskilda oläsbara meddelanden är hanterade: de hoppas
                    # över och resten av pollningen lyckas. Det är ett
                    # datakvalitetsproblem, inte ett driftfel -- och ska inte
                    # loggas som ERROR var femte minut.
                    _logger.info(
                        'Mail poll: %s hoppade över %s oläsbara meddelanden '
                        '(%s nya lästes).',
                        user.login, failed, new)
            except Exception as e:
                _logger.error(
                    'Mail poll failed for user %s (%s): %r',
                    user.login, user.id, e, exc_info=True)
        self._report_progress(total, 0)
        return total

    def action_poll_user(self, deadline=None):
        """Poll ONE user's INBOX (env.user = target user).

        Returnerar ``(nya_meddelanden, normaliseringsfel)``. Det andra värdet
        låter anroparen skilja ett trasigt enskilt mail (hanterat, loggat som
        WARNING, pollningen fortsätter) från ett anslutningsfel (som ska synas
        som ERROR). Tidigare bubblade ingetdera upp — men inget gick heller
        att skilja åt i efterhand.

        Readonly-säker: använder BODY.PEEK så att \\Seen aldrig sätts och
        inga flaggor/mappar ändras.

        Inkrementellt: hämtar endast UID:n efter användarens cursor.
        Dedup sker på headers INNAN full body hämtas, så redan processade
        mail kostar inget. Budgeten kontrolleras mellan meddelanden —
        aldrig mitt i ett.

        Minne: råbytes bärs aldrig i den normaliserade listan. De går via
        `raw_sink` till `_on_new_message_raw()` medan de ännu finns i
        handen, så att en poll av N mail inte ackumulerar N meddelanden
        i minnet samtidigt (INC-2026-10-19).
        """
        user = self.env.user
        budget = self._poll_param('poll_budget_seconds', 30)
        chunk = self._poll_param('poll_chunk_size', 25)
        if deadline is None:
            deadline = time.monotonic() + budget
        started = time.monotonic()
        conn = self._connect_imap()
        try:
            uidvalidity = self._uidvalidity(conn, 'INBOX')
            cursor = user.last_imap_uid or 0
            resync = False
            if user.last_imap_uidvalidity and uidvalidity \
                    and user.last_imap_uidvalidity != uidvalidity:
                # UID:n är inte längre jämförbara — börja om från början.
                _logger.info(
                    'IMAP poll: resync for %s — UIDVALIDITY %s -> %s',
                    user.login, user.last_imap_uidvalidity, uidvalidity)
                cursor = 0
                resync = True
            uids = self._candidate_uids(conn, cursor, 'INBOX')
            if not user.last_imap_uid:
                _logger.info(
                    'IMAP poll: resync for %s — no cursor (candidates=%d)',
                    user.login, len(uids))
            processed = set(self._get_processed_message_ids(user.id))
            headers = self._fetch_headers(conn, uids)
            dedup_skipped = 0
            spam_skipped = 0
            parse_errors = 0
            fetched = 0
            messages = []
            highest = cursor
            normalize_failures = 0
            for uid in uids:
                if time.monotonic() >= deadline:
                    break
                hdr = headers.get(uid) or {}
                key = self._dedup_key({
                    'message_id': hdr.get('message_id', ''),
                    'from_': hdr.get('from_', ''),
                    'subject': hdr.get('subject', ''),
                    'date': hdr.get('date', ''),
                })
                if key and key in processed:
                    dedup_skipped += 1
                    highest = max(highest, uid)
                    continue
                # Spam avgörs på headers, FÖRE body-fetch och FÖRE
                # normalisering: ett spam-mail ska aldrig kosta en
                # MIME-parse eller nå triage-pipelinen.
                if self._is_spam(hdr.get('spam_headers')):
                    spam_skipped += 1
                    self._record_processed(
                        user.id, [{'dedup_key': key or 'uid:%d' % uid}],
                        skip_reason='spam')
                    highest = max(highest, uid)
                    continue
                typ2, msg_data = conn.uid('FETCH', str(uid), '(BODY.PEEK[])')
                fetched += 1
                if (typ2 != 'OK' or not msg_data
                        or not isinstance(msg_data[0], tuple)):
                    continue
                _flags_raw, raw = msg_data[0]
                try:
                    norm = self._normalize_message(
                        raw, folder='INBOX', uid=uid,
                        raw_sink=self._on_new_message_raw)
                except Exception as e:
                    parse_errors += 1
                    normalize_failures += 1
                    reason = '%s: %s' % (type(e).__name__, e)
                    _logger.warning(
                        'Normalize failed for %s uid=%s: %r',
                        user.login, uid, e, exc_info=True)
                    # Poison-policy: framsteg framför fullständighet.
                    self._record_processed(
                        user.id, [{'dedup_key': key or 'uid:%d' % uid}],
                        failed=True, failure_reason=reason)
                    highest = max(highest, uid)
                    continue
                # Släpp råbytes direkt — de behövs inte längre.
                del raw
                if not norm:
                    continue
                messages.append(norm)
                highest = max(highest, uid)
                if len(messages) >= chunk:
                    break
            # Framstegsmarkören skrivs FÖRE konsumtionen. Kraschar den (som
            # LOGOUT-felen gjorde 2026-10-19) hämtas annars samma mail igen
            # nästa körning — och minnesfotavtrycket upprepas utan att något
            # nytt tillförs. Dedup-tabellen `user.mail.processed` är
            # retry-vägen för ett mail som bearbetats men inte konsumerats.
            remaining = len([u for u in uids if u > highest])
            user.write({
                'last_imap_sync': fields.Datetime.now(),
                'last_imap_uid': highest,
                'last_imap_uidvalidity': uidvalidity,
            })
            if messages:
                self._on_new_messages(messages)
                self._record_processed(user.id, messages)
                # Nytt mail i mappen: listvyn ska visa det direkt, inte
                # efter TTL. Pollern läser bara INBOX idag.
                _invalidate_folder_cache(user.id, 'INBOX')
            elapsed = time.monotonic() - started
            _logger.info(
                'IMAP poll: user=%s candidates=%d new=%d dedup_skipped=%d '
                'spam_skipped=%d parse_errors=%d fetched=%d elapsed=%.1fs '
                'remaining=%d resync=%s',
                user.login, len(uids), len(messages), dedup_skipped,
                spam_skipped, parse_errors, fetched, elapsed, remaining,
                resync)
            self._report_progress(len(messages), remaining)
            return len(messages), normalize_failures
        finally:
            _safe_logout(conn)
            _report_logout_failures(user.login)

    def _on_new_message_raw(self, norm, raw_bytes):
        """Hook: ett normaliserat mail + dess råbytes, medan de finns.

        Anropas av `_normalize_message` via `raw_sink` — INNAN det
        normaliserade mailet läggs i poll-listan. Bryggmoduler som behöver
        `.eml`-arkivering (user_mail_ai) kan skriva bilagan här i stället
        för att bära bytesen genom hela pipelinen.

        Default: no-op. Råbytesen släpps när anropet returnerar.
        """
        return None

    def _get_processed_message_ids(self, user_id):
        """Alla redan processade dedup-nycklar för användaren."""
        return self.env['user.mail.processed'].sudo().search(
            [('user_id', '=', user_id)]).mapped('message_id')

    # ── Cursor (UID) ──────────────────────────────────────────────

    def _uidvalidity(self, conn, folder='INBOX'):
        """Läs mappens UIDVALIDITY ur SELECT-svaret.

        UID:n är bara jämförbara inom samma UIDVALIDITY. Ändras värdet
        (mappen återskapad, Dovecot-omindexering) måste cursorn nollställas
        — annars hoppar vi tyst över mail.
        """
        # `select()` returnerar BARA EXISTS — antalet meddelanden:
        #
        #     return typ, self.untagged_responses.get('EXISTS', [None])
        #
        # UIDVALIDITY ligger i `untagged_responses` och måste läsas med
        # `response()`. Den tidigare versionen letade efter "UIDVALIDITY nnn"
        # i EXISTS-svaret, hittade aldrig något och returnerade alltid None --
        # så resync-detekteringen kunde aldrig slå till och ett UIDVALIDITY-
        # byte hade tyst hoppat över mail.
        typ, _data = conn.select(_quote_mailbox(folder))
        if typ != 'OK':
            return None
        res = conn.response('UIDVALIDITY')
        if not isinstance(res, tuple) or len(res) != 2:
            return None
        _key, values = res
        if not values:
            return None
        first = values[0]
        if isinstance(first, bytes):
            first = first.decode('ascii', 'ignore')
        first = str(first or '').strip()
        # imaplib lagrar hela den bracketerade koden, t.ex. b'UIDVALIDITY
        # 1712345678' (eller bara b'1712345678' beroende på server). Ta
        # sista ordet så båda formerna fungerar.
        if not first:
            return None
        return first.split()[-1] or None

    def _candidate_uids(self, conn, cursor, folder='INBOX'):
        """UID:n efter cursorn — O(nya mail), inte O(brevlåda).

        `UID SEARCH UID <n+1>:*` är svaret på "vad är nytt sedan sist".
        Utan cursor (första körningen eller efter UIDVALIDITY-byte) faller
        vi tillbaka på ALL och gör en engångs-omsynkronisering.
        """
        crit = 'UID %d:*' % (cursor + 1) if cursor else 'ALL'
        res = conn.uid('SEARCH', crit)
        if not isinstance(res, tuple) or len(res) != 2:
            return []
        typ, data = res
        if typ != 'OK' or not data:
            return []
        raw = data[0]
        if not raw:
            return []
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8', 'ignore')
        return [int(u) for u in str(raw).split() if str(u).isdigit()]

    # ── Spam (header-baserat, före body-fetch) ────────────────────

    # Tak för hur många unika header-fält vi lägger i HEADER.FIELDS.
    # Skyddar mot en konfiguration med orimligt många regler.
    _SPAM_MAX_FIELDS = 20

    def _spam_rules(self):
        """Läs spam-reglerna ur ir.config_parameter.

        Format: [{"header": "X-Spam-Flag", "match": "YES"}, ...]

        Trasig JSON ger en tom lista och en varning — ett konfigurationsfel
        ska aldrig stoppa pollningen. Tom lista = filtret avstängt.
        """
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'user_mail_imap.spam_headers', '')
        if not raw:
            return []
        try:
            rules = json.loads(raw)
        except (ValueError, TypeError) as e:
            _logger.warning(
                'Spam-regler: trasig JSON i user_mail_imap.spam_headers '
                '(%s: %s) — spam-filtret är avstängt tills den rättas.',
                type(e).__name__, e)
            return []
        if not isinstance(rules, list):
            _logger.warning(
                'Spam-regler: user_mail_imap.spam_headers ska vara en lista, '
                'fick %s — filtret är avstängt.', type(rules).__name__)
            return []
        clean = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            header = (rule.get('header') or '').strip()
            match = rule.get('match')
            if not header or match is None:
                continue
            clean.append({'header': header, 'match': str(match)})
        return clean

    def _spam_header_names(self):
        """Unika header-namn för HEADER.FIELDS (deduplicerade, takade)."""
        seen = []
        for rule in self._spam_rules():
            name = rule['header'].upper()
            if name not in seen:
                seen.append(name)
            if len(seen) >= self._SPAM_MAX_FIELDS:
                break
        return seen

    def _is_spam(self, headers):
        """Avgör på headers om ett mail är spam.

        `headers` är dict med headernamn (versaler) -> värde. Matchningen är
        skiftlägesokänslig och träffar när värdet BÖRJAR med regelns `match`,
        så `X-Spam-Status: Yes, score=8.2 ...` träffar `Yes`.

        Utan regler, eller när ingen header matchar, returneras False —
        då behandlas mailet som vanligt mail (dagens beteende).
        """
        if not headers:
            return False
        for rule in self._spam_rules():
            value = headers.get(rule['header'].upper())
            if not value:
                continue
            if str(value).strip().lower().startswith(
                    rule['match'].strip().lower()):
                return True
        return False

    def _fetch_headers(self, conn, uids):
        """Hämta headers för en UID-mängd — dedup-nycklar OCH spam-fält.

        Dedup ska ske INNAN full body hämtas. Ett enda FETCH för hela
        mängden ger oss dedup-nycklarna billigt; full body hämtas sedan
        endast för de UID:n som är nya.

        Spam-fälten (se `_spam_header_names`) läggs i SAMMA HEADER.FIELDS —
        avgörandet kostar därför ingen extra IMAP-rundtur.

        Returns dict: uid -> {message_id, from_, subject, date, spam_headers}
        där `spam_headers` är headernamn (versaler) -> värde för de fält
        spam-reglerna pekar på.
        """
        if not uids:
            return {}
        fields = ['MESSAGE-ID', 'FROM', 'SUBJECT', 'DATE']
        for name in self._spam_header_names():
            if name not in fields:
                fields.append(name)
        out = {}
        for batch in _uid_batches(uids):
            uid_set = ','.join(str(u) for u in batch)
            typ, data = conn.uid(
                'FETCH', uid_set,
                '(UID BODY.PEEK[HEADER.FIELDS (%s)])' % ' '.join(fields))
            if typ != 'OK':
                continue
            self._parse_header_batch(data, out, fields)
        return out

    def _parse_header_batch(self, data, out, fields):
        """Parsa ett FETCH-svar med headers in i `out` (uid -> dict)."""
        current_uid = None
        for item in data or []:
            if isinstance(item, tuple):
                meta, raw = item[0], item[1]
                if isinstance(meta, bytes):
                    meta = meta.decode('utf-8', 'ignore')
                m = re.search(r'UID\s+(\d+)', meta or '')
                if not m:
                    continue
                current_uid = int(m.group(1))
                try:
                    msg = BytesParser(policy=policy.default).parsebytes(raw)
                    spam_headers = {}
                    for name in fields:
                        if name in ('MESSAGE-ID', 'FROM', 'SUBJECT', 'DATE'):
                            continue
                        value = msg.get(name)
                        if value is not None:
                            spam_headers[name] = str(value)
                    out[current_uid] = {
                        'message_id': str(msg.get('Message-ID', '')).strip(),
                        'from_': str(msg.get('From', '')),
                        'subject': str(msg.get('Subject', '')),
                        'date': str(msg.get('Date', '')),
                        'spam_headers': spam_headers,
                    }
                except Exception as e:
                    _logger.warning(
                        'Header parse failed uid=%s: %s: %s',
                        current_uid, type(e).__name__, e)

    def _record_processed(self, user_id, messages, failed=False,
                          failure_reason=None, skip_reason=None):
        """Beständig dedup: spara Message-ID/dedup-nyckel per användare.

        `skip_reason` skiljer ett medvetet överhoppat mail (t.ex. spam) från
        ett misslyckat. Bara `failed` räknas som parse-fel i `_poll_health()`
        — spam är ett förväntat utfall, inte ett fel.
        """
        vals = []
        for m in messages:
            key = m.get('dedup_key')
            if not key:
                continue
            vals.append({
                'user_id': user_id,
                'message_id': key,
                'failed': failed,
                'failure_reason': failure_reason,
                'skip_reason': skip_reason,
            })
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

    def _normalize_message(self, raw_bytes, folder='INBOX', uid=None,
                           raw_sink=None):
        """Parsa en rå RFC822-message till den normaliserade dict-formen.

        Returns dict: message_id, subject, from_, to_, date, body_text,
        body_html, attachments (list of {filename, content_type}), folder,
        thread_refs och dedup_key.

        **Råbytes bärs INTE med.** Fältet `raw` kopierade hela meddelandet
        (inklusive bilagor) in i dict:en, och eftersom en poll bygger en
        lista av alla normaliserade mail låg hela brevlådan i minnet
        samtidigt. Mätt 2026-10-19: RSS 500 MB -> 2 336 MB på sju minuter,
        med `virtual memory limit reached` 0,1-0,3 s efter pollens slut.

        Den som behöver råbytes (för `.eml`-arkivering) skickar in dem via
        `raw_sink` — en callable som tar emot bytesen medan de ännu finns
        i handen, i stället för att de ackumuleras i listan.
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
        # Trådreferenser behövs för objektmatchning. De är korta strängar —
        # att bära dem kostar inget, och det gör att konsumenten slipper
        # parsa om hela meddelandet.
        thread_refs = []
        for header in ('References', 'In-Reply-To'):
            val = msg.get(header) or ''
            thread_refs += re.findall(r'<[^>]+>', str(val))
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
            'thread_refs': thread_refs,
        }
        norm['dedup_key'] = self._dedup_key(norm)
        # Råbytes lämnas vidare HÄR, medan de ännu finns i handen. Att
        # returnera dem i dict:en vore att ackumulera hela brevlådan i
        # minnet under en poll (se docstringen ovan).
        if raw_sink is not None:
            try:
                raw_sink(norm, raw_bytes)
            except Exception as e:
                _logger.warning(
                    'Raw sink failed uid=%s: %s: %s',
                    uid, type(e).__name__, e)
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
                    _select_folder(conn, folder)
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
            _select_folder(conn, folder)
            for batch in _uid_batches(uids):
                uid_list = ','.join(str(u) for u in batch)
                typ, _data = conn.uid('MOVE', uid_list, _quote_mailbox(to_folder))
                if typ != 'OK':
                    # Fallback: COPY + \Deleted + EXPUNGE
                    conn.uid('COPY', uid_list, _quote_mailbox(to_folder))
                    conn.uid('STORE', uid_list, '+FLAGS', '\\Deleted')
                    conn.expunge()
            return True
        finally:
            _safe_logout(conn)
            # Både käll- och målmappens sidor är inaktuella.
            _invalidate_folder_cache(self.env.user.id, folder)
            _invalidate_folder_cache(self.env.user.id, to_folder)

    def action_ensure_folder(self, folder):
        """Skapa mapp om den inte finns (best-effort)."""
        conn = self._connect_imap()
        try:
            try:
                conn.create(_quote_mailbox(folder))
                return True
            except Exception:
                return False
        finally:
            _safe_logout(conn)

    def action_fetch_draft_raw(self, folder, uid):
        """Hämta råa innehållet i ett utkast (för HITL-skick)."""
        conn = self._connect_imap()
        try:
            _select_folder(conn, folder)
            # UID, inte sekvensnummer (se action_fetch_mail).
            typ, data = conn.uid('FETCH', str(uid), '(BODY.PEEK[])')
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
