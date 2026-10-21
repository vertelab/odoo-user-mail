# Design: Server-side Sieve — vacation and rules

## Module placement

`user_mail_common` is the base of both branches, so the Sieve layer lives
there. No new module.

```
user_mail_common        ← sieve.script, ManageSieve client, compiler
      ↑              ↑
user_mail_client   user_mail_imap
   (vacation UI)        ↑
                   user_mail_ai
                     (rules: ai + sieve)
```

Rationale: `user_mail_client` (where the vacation view lives) does **not**
depend on `user_mail_imap`. Putting Sieve in `user_mail_imap` would force
the client module to pull in the whole IMAP client; putting it in
`user_mail_ai` would make vacation depend on the AI assistant. The base
module is the only place both branches can reach.

Cost: `user_mail_common` gains `sievelib` as an external dependency. It is
already in `requirements.txt` and verified importable.

## Data model

### `sieve.script` — one per user, the generated script

```python
class SieveScript(models.Model):
    _name = 'sieve.script'
    _description = 'Generated Sieve script'

    user_id    = Many2one('res.users', required, ondelete='cascade', index)
    name       = Char('Script name', default='odoo_ai')   # ManageSieve name
    body       = Text('Generated Sieve')                  # what we push
    state      = Selection([('draft','Not synced'),
                            ('synced','Synced'),
                            ('error','Error')], default='draft')
    last_sync  = Datetime()
    last_error = Text()
    active     = Boolean(default=True)   # is this script the ACTIVE one
```

`_sql_constraints`: `unique(user_id)` — one script per user.

Why a separate model and not fields on `res.users`: the generated script is
derived output, it has its own sync state and error, and it must be
inspectable without opening a user form.

### `res.users` — vacation fields (already exist, unchanged)

```python
vacation_active, vacation_subject, vacation_text,
vacation_from, vacation_to, vacation_forward
```

`vacation_forward` is **not** compiled into Sieve (see Non-goals). The field
stays; it is currently inert and remains so.

## ManageSieve client

Lives on `user.mail.imap`? **No** — `user_mail_imap` is not reachable from
`user_mail_common`. Instead a small client class in
`user_mail_common/models/sieve_client.py`, used by `sieve.script`:

```python
def _connect(self):
    """ManageSieve connection reusing the stored IMAP password."""
    from sievelib.managesieve import Client
    imap = self.env['ir.config_parameter']  # host/port
    return Client(host, port).connect(login, password, starttls=True)
```

Password source: `res.users.dovecot_password` (already stored, already used
by the IMAP poller). No new credential.

Connection parameters come from `odoo.conf` (`imap_host`, `imap_port`) with
ManageSieve defaults `4190` and STARTTLS. Verified working against
`imap.vertel.se:4190`.

## Compiler: rules → Sieve

`user_mail_ai.rule` records with `enforcement='server'` are compiled with
`sievelib.factory.FiltersSet`:

```python
fs = FiltersSet('odoo_ai')
for rule in rules:
    fs.addfilter(rule.name, conditions, actions)
```

### Condition mapping

| `condition_kind` | Sieve |
|---|---|
| `sender` | `('from', ':contains', text)` |
| `subject` | `('subject', ':contains', text)` |
| `category` | not expressible — skipped (see below) |
| `llm` | not expressible — stays client-side |

### Action mapping

| `action` | Sieve |
|---|---|
| `move_to_folder` | `('fileinto', ':create', folder)` |
| `flag` | `('addflag', '\\Flagged')` |
| `ignore` / `block` | `('discard',)` |
| `nudge`, `draft_reply`, `create_object`, `create_activity`, `create_event`, `send_to_specialist` | not expressible — stay client-side |

**Verified pitfalls (all confirmed against the live server):**

1. Conditions are `(header-name, operator, value)` — **not**
   `('header', ':contains', ...)`. `header` is the test command sievelib
   builds internally.
2. Mailbox names are passed **unquoted**: `'INBOX.Linkedin mm'`. sievelib
   quotes them. Passing `'"INBOX.X"'` yields `"\"INBOX.X\""`.
3. `:days` takes an **int** (`7`), not a string — a string raises `BadValue`.
4. `currentdate :value "ge"` requires `require ["relational"]`. Without it
   the server rejects the script.

### Validation before push

```python
if not Parser().parse(sieve_text):
    raise UserError(...)
if not client.checkscript(sieve_text):
    raise UserError(client.errmsg)
```

`checkscript` is a server-side compile — it catches what the local parser
cannot. Never `putscript` a script that fails either check.

## Vacation

Compiled into the user's own script, **never** into `default.sieve`.

```sieve
require ["vacation"];

if true {
    vacation :days 7
             :from "anders.wallenquist@vertel.se"
             :subject "Semester"
             "Jag är på semester och återkommer 2026-10-15.";
}
```

`:from` is verified accepted by the server. The sender address is the
user's own (`postfix_mail`), not postmaster.

### Mail ping-pong protection

Three layers, in order of importance:

1. **`:days 7`** — Pigeonhole sends at most one reply per sender per 7 days.
   This is the primary loop brake and it is built into the extension.
2. **No `redirect` in the vacation rule.** `redirect` has no equivalent
   rate limit. A vacation that also redirects is the classic loop: two
   people on holiday forwarding to each other, `MAXREDIRECTS 4` is a
   ceiling on one message, not on the loop.
3. **Pigeonhole skips auto-generated mail** (`Auto-Submitted`,
   `Precedence: bulk`, `List-Id`) on its own. No code needed.

`vacation_forward` is therefore **not** compiled. If the user wants
forwarding, `forward_active`/`forward_address` is the existing mechanism
and belongs in a separate rule, not inside vacation.

### From/To dates: cron, not Sieve

`currentdate` exists but requires `relational` and produces a script that
must still be cleaned up after the period. A daily cron is simpler and
keeps one source of truth:

```python
# ir.cron, daily
for user in users_with_vacation_active:
    today = fields.Date.context_today(user)
    in_range = (not user.vacation_from or user.vacation_from <= today) \
           and (not user.vacation_to   or user.vacation_to   >= today)
    user._sieve_sync_vacation(active=in_range)
```

The cron writes the vacation block when in range and removes it when out.
`vacation_active` remains the user's switch; the dates narrow it.

## Rules: `enforcement` on `user_mail_ai.rule`

```python
enforcement = fields.Selection([
    ('client', 'I Odoo (efter hämtning)'),
    ('server', 'På servern (Sieve)'),
], default='client', required=True)
```

`_apply_rules()` in `user_mail_ai_intelligence.py` skips rules where
`enforcement == 'server'` — the server already handled them. Without this
a mail would be moved twice.

A rule with `enforcement='server'` and an action Sieve cannot express
(`create_object`, `nudge`, …) is a **validation error**, not a silent
downgrade. The user must not believe a rule runs on the server when it
does not.

## UI

### Vacation (user_mail_client view — already exists)

No new fields. The existing group gains nothing; it starts working.

### Rule dialog from a mail (user_mail_ai)

Button in `mail_detail.xml` next to Reply/Forward:

```xml
<button class="btn btn-sm btn-outline-secondary"
        t-on-click="() => props.openRuleDialog(props.message)">
    <i class="fa fa-filter me-1"/>Skapa regel
</button>
```

Dialog pre-fills from the selected message:
- sender → `condition_kind='sender'`, `condition_text=<from>`
- subject → `condition_kind='subject'`
- folder suggestion from `action_list_folders()`
- `enforcement='server'` preselected (the common case is sorting)

### Script tab on the rule form

Read-only `body` plus `state`/`last_error`, so a failed sync is visible
rather than silent.

## Sync

```
rule create/write/unlink  →  res.users._sieve_rebuild()  →  sieve.script
sieve.script.write()      →  validate → putscript → setactive
```

Rebuild is idempotent: the whole script is regenerated from the rule set,
never patched. That keeps Odoo the single source of truth and makes a
hand-edited server script impossible to half-merge.

## Non-goals

- `vacation_forward` → Sieve. Skipped: loop risk, and `forward_active`
  already exists.
- `category` and `llm` conditions on the server. Not expressible in Sieve.
- Vacation in `default.sieve`. It is one global file; a per-user vacation
  there would fire for every user.
- A raw Sieve editor.
- Deployment.
