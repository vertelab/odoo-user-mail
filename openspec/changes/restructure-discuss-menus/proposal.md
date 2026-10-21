# Proposal: Restructure the Discuss mail menus

## Why

The mail menus have grown by accretion. Each module added its own root entry
under Discuss, so there are now **three sibling roots** where there should be
one hierarchy:

```
Diskutera
├── Imap-mail              (user_mail_imap, seq 99)
├── Mail-hjälpredan        (user_mail_ai,   seq 100)
└── Inställningar          (user_mail_common, seq 90)
    ├── E-postkonfiguration
    ├── Regler
    └── Serverregler (Sieve)
```

Three problems, in order of how much they cost the user:

1. **"Inställningar" collides with Odoo's own Discuss → Configuration**
   (`mail.menu_configuration`, already translated to "Konfiguration" in
   Swedish). Two menus that both read as "settings" under the same root is a
   coin flip for the user.

2. **"Regler" and "Serverregler (Sieve)" look like two kinds of rule.** They
   are not. They are the same `user_mail_ai.rule` record, split by the
   `enforcement` field: `client` rules run in Odoo after fetch, `server` rules
   are compiled into Sieve and run at delivery. A user who creates a rule in
   one menu cannot find it in the other, and concludes it was not saved.

   "Serverregler (Sieve)" is not even a rule list — it is the generated
   `sieve.script` (read-only body, sync state, last error). It is a *status
   view*, not a place to manage rules.

3. **"Mail-hjälpredan" is a fourth name for the same feature.** It is the
   AI triage inbox (`user_mail_ai.mail`), which is a mail list, not a
   settings page — but sitting next to two settings-ish menus it reads as
   configuration.

The user's own words: *"Fråga varför skilja på Regler och Sieve-regler i
menyn (Behövs Mail-hjälpredan?)"* — the split is not defensible, and the
proposal should answer whether Mail-hjälpredan earns its place.

## What changes

Target structure:

```
Diskutera
└── E-post                            (new root, user_mail_common)
    ├── Imap-mail                     (the mail client)
    ├── Mail-hjälpredan               (AI triage inbox)
    ├── E-postkonfiguration           (own user form, E-mail settings tab)
    ├── Regler                        (all rules, both enforcements)
    └── Serverregler (Sieve)          (script status — renamed)
```

Changes:

- **One root** `E-post` under Discuss, owned by `user_mail_common`. The three
  current roots become children. `user_mail_ai` and `user_mail_imap` cannot
  own a shared root (neither depends on the other), which is why it lives in
  the base module — same reasoning as the existing `menu_user_mail_settings`.

- **"Inställningar" disappears** as a name. Its children move up to the new
  root. This removes the collision with `mail.menu_configuration`.

- **"Regler" shows all rules.** The action already uses
  `{'active_test': False}`; it gains no `enforcement` filter. The form gets
  the `enforcement` field (already added in `add-sieve-rules`), so the
  distinction is visible *inside* a rule instead of as two menus.

- **"Serverregler (Sieve)" is renamed** to make clear it is status, not
  management: **"Sieve-status"**. It keeps the script view — that is where a
  failed sync is visible, and it must not be hidden.

- **`E-postkonfiguration` opens the user's own form** at the "E-mail settings"
  tab. Already implemented as an `ir.actions.server` returning an act_window
  with `res_id = env.uid`; unchanged by this proposal apart from its parent.

## Open question — does Mail-hjälpredan belong?

The user asked. The honest answer is **yes, but it is mis-parented today**.

It is not a settings page and not a duplicate of Imap-mail:

| | Imap-mail | Mail-hjälpredan |
|---|---|---|
| Shows | raw mail from IMAP | messages after AI triage |
| Data | live IMAP folders | `user_mail_ai.mail` records |
| Purpose | read and send mail | review classification, rules, handoffs |
| Works without AI | yes | no |

So it stays — but under `E-post` as a sibling of Imap-mail, not as a
third root. If the AI module is not installed the menu is absent anyway,
because it is defined in `user_mail_ai`.

**Decision needed:** keep the name "Mail-hjälpredan", or rename to something
that says what it is (e.g. "AI-inkorg")? Keeping it is the smaller change;
renaming costs a `sv.po` entry and user retraining.

## Non-goals

- No change to what any of the actions do — only where they hang.
- No change to rule semantics, `enforcement`, or the Sieve compiler.
- No merging of `user_mail_ai.mail` and the IMAP message list. They are
  different data with different lifetimes.
- No new module. All menu records stay where they are; only `parent` and
  `sequence` change.

## Risks

- **Existing user bookmarks.** Anyone who has bookmarked a menu URL keeps a
  working action — menu ids are unchanged, only their parent. Low risk.

- **`groups` on the root.** The new root must carry
  `user_mail_common.group_own_email_settings`, or users without it see an
  empty "E-post" menu. The children already carry their own groups; the root
  must not be more permissive than its children.

- **Ordering.** `menu_user_mail_settings` is currently `sequence 90` under
  Discuss. Moving it under a new root changes what the user sees at the top
  level: one "E-post" entry instead of three. That is the point, but it is a
  visible change and should be mentioned in the release note.

- **The old root must be removed, not orphaned.** Leaving
  `menu_user_mail_settings` in place with no children produces an empty
  "Inställningar" menu under Discuss.
