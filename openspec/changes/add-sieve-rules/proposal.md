# Proposal: Server-side Sieve rules created from a mail

## Why

Today a user's mail rules (`user_mail_ai.rule`) are applied **client-side**:
the IMAP poller fetches a message, the AI assistant classifies it, and only
then does Odoo move it to a folder or set a flag. Three consequences:

1. **Mail sits in INBOX until the poller runs.** A rule cannot prevent a
   newsletter from appearing in the inbox; it can only relocate it later.
2. **Rules die with the poller.** If the Odoo cron is down, or the user
   reads mail in another client, no rule is applied at all.
3. **The most common rule — "sort this into a folder" — is the one that
   benefits most from running at delivery time.**

Dovecot already runs Sieve at delivery (LMTP). ManageSieve is already
listening on `imap.vertel.se:4190` with `fileinto`, `imap4flags` and
`variables` available. The server-side machinery exists; only the Odoo
side is missing.

The user also wants to **create a rule from a mail they are reading**: pick
a message, press a button in the mail header, get a dialog pre-filled from
that message, adjust, save. The rule then goes to the server.

## What changes

Extend the existing `user_mail_ai.rule` model with an `enforcement` field
rather than introducing a parallel Sieve model. A Sieve rule is the same
rule with a different execution point — it should inherit priority,
active/inactive, conditions and the AI assistant's ability to maintain it.

```
enforcement = 'client'  → applied by the poller (current behaviour)
enforcement = 'server'  → compiled to Sieve and pushed via ManageSieve
```

New pieces:

- **`sieve.script`** — one record per user holding the generated script
  text, the ManageSieve script name, sync state and last error.
- **`user.mail.imap`** — ManageSieve client methods: connect, list, get,
  put, setactive, delete. Reuses the stored IMAP password.
- **Sieve compiler** — `user_mail_ai.rule` records → Sieve source via
  `sievelib.factory.FiltersSet`.
- **UI** — "Create rule" button in the mail header, opening an OWL dialog
  pre-filled from the selected message; a "Sieve" tab on the rule form
  showing the generated script.

### Decisions taken

| Question | Decision |
|---|---|
| One script or take over `arkiv`? | **Own script.** Odoo owns a script named `odoo_ai` and activates it. The user's hand-written `arkiv` is never touched. |
| `sieve_before` / `default.sieve`? | **Use `default.sieve`.** Odoo writes the generated script to `/var/lib/dovecot/sieve/default.sieve` (via Salt), so rules apply to every user without per-user ManageSieve writes being the only path. Per-user scripts remain supported. |
| Conflict with client-side rules? | **`enforcement='server'` suppresses the Odoo-side action.** `_apply_rules()` skips rules whose enforcement is `server`; the server already handled them. |

## Non-goals

- **Not** a Sieve editor. The user never sees Sieve syntax unless they open
  the generated-script tab. No raw script editing in the UI.
- **Not** replacing the AI assistant's rules. `enforcement='client'` rules
  keep working exactly as today.
- **Not** implementing vacation/auto-reply, `reject`, or `enotify`. Only
  the actions the rule model already expresses: file into folder, set flag,
  mark read, discard.
- **Not** touching `dovecot`/`dovecot.sieve` internal folders (already
  filtered in `action_list_folders`).
- **No deployment in this change.** Deploying is a separate decision.

## Impact

| Area | Change |
|---|---|
| `user_mail_ai.rule` | + `enforcement`; `_apply_rules()` skips server rules |
| new `sieve.script` | generated text, sync state, error |
| `user.mail.imap` | ManageSieve client methods |
| `user_mail_ai` manifest | + `sievelib` external dependency |
| OWL | `mail_detail.xml` button, new rule dialog, rule form tab |
| Salt | state writing `default.sieve` |
| Tests | compiler round-trip, sync against a fake server |

## Risk

- **Silent rule loss.** If a sync fails the user believes the rule is live.
  Mitigation: `sieve.script.state` + `last_error`, shown in the UI.
- **Malformed Sieve breaks delivery.** A syntax error in the active script
  can make Dovecot reject or misfile mail. Mitigation: validate with
  `sievelib.parser` before `putscript`; never activate a script that fails
  to parse.
- **Two sources of truth.** A rule edited in Odoo and a script edited by
  hand on the server can drift. Mitigation: Odoo owns `odoo_ai`; hand-edited
  scripts are out of scope and never overwritten.
