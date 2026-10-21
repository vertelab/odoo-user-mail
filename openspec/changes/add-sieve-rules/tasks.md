# Tasks: Server-side Sieve — vacation and rules

Deployment is **not** a task here. It is a separate decision after review.

## Phase 1 — Foundation (`user_mail_common`)

- [ ] 1.1 Add `sievelib>=1.6,<2` to `user_mail_common/__manifest__.py`
      `external_dependencies`
- [ ] 1.2 Create `models/sieve_script.py` — `sieve.script` model:
      `user_id`, `name`, `body`, `state`, `last_sync`, `last_error`,
      `active`; `unique(user_id)` constraint
- [ ] 1.3 Create `models/sieve_client.py` — ManageSieve wrapper:
      `_connect()` (host/port from `ir.config_parameter`, password from
      `res.users.dovecot_password`, STARTTLS), `checkscript()`,
      `putscript()`, `setactive()`, `listscripts()`
- [ ] 1.4 Add `security/ir.model.access.csv` rows — user reads/writes own
      script; `base.group_erp_manager` full
- [ ] 1.5 Add record rule — a user sees only their own `sieve.script`
- [ ] 1.6 `res.users._sieve_script()` — get-or-create the user's script
- [ ] 1.7 `sieve.script._validate(body)` — `sievelib.parser.Parser().parse()`
      then `checkscript()`; raise `UserError` with the server's `errmsg`
- [ ] 1.8 `sieve.script.action_sync()` — validate → `putscript` →
      `setactive`; on failure set `state='error'` + `last_error`, never
      raise past the cron

## Phase 2 — Vacation (`user_mail_common` + `user_mail_client`)

- [x] 2.1 `res.users._sieve_vacation_block()` — build the vacation Sieve
      fragment: `require ["vacation"]`, `vacation :days 7 :from <postfix_mail>
      :subject <vacation_subject> <vacation_text>`
- [x] 2.2 `res.users._sieve_sync_vacation(active)` — insert or remove the
      block from the script body, then `action_sync()`
- [x] 2.3 `ir.cron` daily (`user_mail_common/data/cron_sieve_vacation.xml`)
      — for each user with `vacation_active`, compute `in_range` from
      `vacation_from`/`vacation_to` vs `context_today`, call
      `_sieve_sync_vacation`
- [x] 2.4 `write()` hook on `res.users` for the vacation fields — resync
      immediately on save, so the user does not wait for the cron
- [x] 2.5 Verify `:from` uses the user's own address (`postfix_mail`), not
      postmaster
- [x] 2.6 Tests: in-range writes the block; out-of-range removes it;
      `vacation_active=False` removes it; `:days 7` present in output
      (ping-pong brake)

## Phase 3 — Rule compiler (`user_mail_common`)

- [x] 3.1 `sieve.script._compile_rules(rules)` — `FiltersSet` →
      `tosieve()`; condition map `sender`→`from`, `subject`→`subject`,
      `category`/`llm` skipped
- [x] 3.2 Action map: `move_to_folder`→`fileinto :create`, `flag`→
      `addflag \Flagged`, `ignore`/`block`→`discard`
- [x] 3.3 Mailbox names passed **unquoted** to `addfilter` (sievelib quotes)
- [x] 3.4 `:days` passed as **int**, not string
- [x] 3.5 Tests: round-trip a rule set through `FiltersSet` → `Parser`;
      assert mailbox with a space is quoted exactly once; assert
      `:days 7` is an int

## Phase 4 — Rules in `user_mail_ai`

- [x] 4.1 Add `enforcement` selection to `user_mail_ai.rule`
      (`client` default, `server`)
- [x] 4.2 `_apply_rules()` skips `enforcement == 'server'` — the server
      already handled it (prevents double move)
- [x] 4.3 `@api.constrains` — `enforcement='server'` with an action Sieve
      cannot express (`nudge`, `draft_reply`, `create_object`,
      `create_activity`, `create_event`, `send_to_specialist`) raises
      `ValidationError`
- [x] 4.4 `create`/`write`/`unlink` on `user_mail_ai.rule` →
      `user._sieve_rebuild()` for server rules
- [x] 4.5 `res.users._sieve_rebuild()` — regenerate the whole script from
      the rule set + vacation block (idempotent, never patched)
- [x] 4.6 Tests: a `server` rule produces Sieve; a `client` rule does not;
      changing a rule rebuilds deterministically

## Phase 5 — UI

- [x] 5.1 "Skapa regel" button in `mail_detail.xml` next to Reply/Forward
- [x] 5.2 OWL dialog `sieve_rule_dialog` — pre-fill sender/subject from the
      selected message, folder picker from `action_list_folders()`,
      `enforcement='server'` preselected
- [x] 5.3 `enforcement` field on the rule form; `body`/`state`/`last_error`
      read-only tab so a failed sync is visible
- [x] 5.4 Frontend: show `sieve.script.last_error` as an alert on the user
      form when `state == 'error'`

## Phase 6 — Verification

- [ ] 6.1 `python3 -m py_compile` on every touched file
- [ ] 6.2 `checkscript` the generated vacation and rule scripts against
      `imap.vertel.se:4190` (verified working in exploration)
- [ ] 6.3 Confirm `currentdate :value "ge"` needs `require ["relational"]`
      — documented, and **not used** (cron is the chosen mechanism)
- [ ] 6.4 Confirm `dovecot`/`dovecot.sieve` still filtered from folder list
- [ ] 6.5 Manual test plan written into the change (see below)

## Manual test plan

1. **Vacation on:** set `vacation_active`, dates spanning today, subject and
   text. Save. Open ManageSieve — the user's script contains
   `vacation :days 7 :from "<own address>"`. Send a mail from an external
   account → auto-reply arrives from the user's own address, not postmaster.
2. **Ping-pong:** send two mails from the same sender within a minute →
   exactly **one** auto-reply (`:days 7`).
3. **Vacation off:** uncheck `vacation_active`. The `vacation` block is gone
   from the script; no auto-reply.
4. **Dates:** set `vacation_to` to yesterday, run the cron → block removed.
5. **Rule from mail:** open a mail, press "Skapa regel", accept the
   pre-filled sender, pick a folder, save. The script gains a
   `fileinto :create` line. Send a matching mail → it lands in the folder.
6. **Folder with a space:** pick `INBOX.Linkedin mm` → script contains
   `fileinto :create "INBOX.Linkedin mm"` with **single** quoting.
7. **No double move:** a `server` rule does not also run in `_apply_rules`.
8. **Bad rule:** set `enforcement='server'` with action `create_object` →
   validation error, not a silent no-op.
9. **Failed sync:** point ManageSieve at a dead host → `state='error'`,
   `last_error` populated, UI shows the alert, no exception escapes the cron.
10. **User isolation:** user A's script never contains user B's rules.
