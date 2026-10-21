# Proposal: Add mail settings to Discuss → Configuration

## Why

The mail modules each added their own root menu under Discuss, so there are
now **three sibling roots** where there should be one:

```
Diskutera
├── Imap-mail              (user_mail_imap, seq 99)
├── Mail-hjälpredan        (user_mail_ai,   seq 100)
└── Inställningar          (user_mail_common, seq 90)
    ├── E-postkonfiguration
    ├── Regler
    └── Serverregler (Sieve)
```

Odoo already has the right home for the last one. Discuss ships a
**Configuration** menu (`mail.menu_configuration`, id 72) holding
Notifications, Voice & Video and Canned Responses. Mail settings belong
there, next to the other Discuss settings — not in a fourth root of our own.

Two further problems with the current layout:

1. **"Regler" and "Serverregler (Sieve)" look like two kinds of rule.** They
   are not. There is one model, `user_mail_ai.rule`, split by the
   `enforcement` field: `client` rules run in Odoo after fetch, `server` rules
   are compiled into Sieve and run at delivery. A user who creates a rule in
   one menu cannot find it in the other, and concludes it was not saved.

   "Serverregler (Sieve)" is not a rule list at all — it is the generated
   `sieve.script` (read-only body, sync state, last error). It is a *status
   view*.

2. **"Inställningar" is a fourth root for three items**, two of which are
   configuration and one of which is status.

## What changes

```
Diskutera
├── Imap-mail                          ← unchanged, top level
├── Mail-hjälpredan                    ← unchanged, top level
└── Konfiguration                      (mail.menu_configuration, Odoo's own)
    ├── Notifications                  (Odoo)
    ├── Voice & Video                  (Odoo)
    ├── Canned Responses               (Odoo)
    ├── E-postinställningar            ← moved here (was E-postkonfiguration)
    └── E-postregler                   ← moved here (was Regler)
```

- **The root "Inställningar" is removed.** Its two settings entries move into
  Odoo's existing Configuration menu, after Canned Responses.

- **"E-postkonfiguration" → "E-postinställningar".** It opens the user's own
  `res.users` form on the "E-mail settings" tab. The new name says what the
  page contains rather than what it configures.

- **"Regler" → "E-postregler".** Same action, no `enforcement` filter — it
  already shows both kinds. The prefix distinguishes it from Odoo's own mail
  settings.

- **"Serverregler (Sieve)" leaves the menu.** It is not a rule list; it is the
  generated `sieve.script` with sync state and last error. Keeping it beside
  "E-postregler" is what created the impression of two rule systems.

  The status must stay reachable — a failed sync has to be visible. It moves
  to a **button on the E-postinställningar page** ("Sieve-status") which opens
  the script view. That is where a user who wonders "are my rules actually
  running?" is already looking.

## Naming

**We do not rename Odoo's Configuration menu.** It stays "Konfiguration" in
Swedish and "Configuration" in English. Whether the label is the best one is a
translation question, not a structural one — and it is not ours to decide by
renaming another module's menu.

The two entries we add are named so they cannot be confused with Odoo's own:
**E-postinställningar** and **E-postregler** both carry the "E-post-" prefix,
which none of Odoo's three children do.

## Non-goals

- No change to what any action does — only names, parents and sequence.
- No change to rule semantics, `enforcement`, or the Sieve compiler.
- No merging of `user_mail_ai.mail` and the IMAP message list.
- No new module. All menu records stay in their current modules.
- No rename of `mail.menu_configuration` or any other Odoo menu.

## Risks

- **Existing user bookmarks.** Menu ids are unchanged, only names and parents,
  so a bookmarked action still opens. Low risk.

- **Removing "Serverregler (Sieve)" from the menu** must not remove the view.
  If the button on E-postinställningar is not added in the same change, the
  only place a failed sync is visible disappears from the UI.

- **Groups.** `mail.menu_configuration` has no group restrictions — every
  internal user sees it. Our two entries must carry
  `user_mail_common.group_own_email_settings` so they are hidden from users
  who cannot use them, rather than showing entries that fail on click.

- **Module dependency.** `user_mail_common` already depends on `mail`, so
  parenting to `mail.menu_configuration` adds no new dependency. Verify the
  same for `user_mail_client` and `user_mail_ai`.

- **Sequence collision.** Odoo's children use 1, 5 and 15. Our entries take
  20 and 30 so they sort after Canned Responses without renumbering Odoo's.
