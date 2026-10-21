# Design: Restructure the Discuss mail menus

## Current state (verified in luke18a, 2026-10-21)

```
mail.menu_root_discuss (71)
├── user_mail_common.menu_user_mail_settings  (512, seq 90)  "Inställningar"
│   ├── user_mail_client.menu_user_mail_own_settings (513, seq 10) "E-postkonfiguration"
│   ├── user_mail_ai.menu_user_mail_ai_rules         (549, seq 20) "Regler"
│   └── user_mail_common.menu_sieve_script           (551, seq 30) "Serverregler (Sieve)"
├── user_mail_imap.menu_user_mail_imap        (514, seq 99)  "Imap-mail"
└── user_mail_ai.menu_user_mail_ai            (548, seq 100) "Mail-hjälpredan"
```

Three roots. The "Inställningar" name collides with
`mail.menu_configuration` (displayed as "Konfiguration").

## Target

```
mail.menu_root_discuss
└── user_mail_common.menu_user_mail_root      (new, seq 90)  "E-post"
    ├── user_mail_imap.menu_user_mail_imap            (seq 10) "Imap-mail"
    ├── user_mail_ai.menu_user_mail_ai                (seq 20) "Mail-hjälpredan"
    ├── user_mail_client.menu_user_mail_own_settings  (seq 30) "E-postkonfiguration"
    ├── user_mail_ai.menu_user_mail_ai_rules          (seq 40) "Regler"
    └── user_mail_common.menu_sieve_script            (seq 50) "Sieve-status"
```

## Decisions

### The root lives in `user_mail_common`

`user_mail_ai` does not depend on `user_mail_imap` (nor the reverse), so
neither can own a menu both hang under. The base module already owns the
current shared root for this reason; the new root replaces it in the same
place. No new dependency edge.

### Reuse the existing root record, do not create a second one

`menu_user_mail_settings` (id 512) is renamed and reparented rather than
deleted and recreated:

```xml
<record id="menu_user_mail_settings" model="ir.ui.menu">
    <field name="name">E-post</field>
    <field name="parent_id" ref="mail.menu_root_discuss"/>
    <field name="sequence">90</field>
</record>
```

The xmlid stays, so every `parent="user_mail_common.menu_user_mail_settings"`
reference in the other modules keeps resolving. Renaming the *xmlid* would
break three modules' menu declarations for no benefit.

**Why not `<delete>`:** Odoo 18 crashes on `<delete>` against a non-existent
xmlid, and a delete+create cycle drops the record id — any user bookmark or
`ir.model.data` reference to 512 becomes dangling. Update in place.

### "Regler" needs no change to its action

`user_mail_ai_rule_action` already has:
- `domain = [('user_id', '=', uid)]` — own rules only
- `context = {'active_test': False}` — inactive rules visible

It does **not** filter on `enforcement`, so it already shows both kinds.
The perceived split came from the menu name "Serverregler (Sieve)" sitting
next to it, implying a second rule list. Renaming that menu to "Sieve-status"
removes the implication; no data change is needed.

### "Sieve-status" keeps the script view

The view is the only place a failed sync is visible (`state='error'`,
`last_error`). It must stay reachable. What changes is the name: "status"
says it is a report, not a place to manage rules.

### `E-postkonfiguration` is unchanged apart from its parent

It is an `ir.actions.server` returning an act_window with `res_id = env.uid`
because `ir.actions.act_window.res_id` is a static integer and cannot
express "the logged-in user". A plain act_window without `res_id` opens a
list, where a normal user gets an access error. This reasoning is unchanged
by the restructure.

The URL the user cited, `/odoo/settings/1/users/25`, is the *admin* path to
a specific user's form. The menu must not hardcode it — it must resolve to
`env.uid` so each user lands on their own record.

### Groups on the root

The new root carries `user_mail_common.group_own_email_settings`, matching
its children. A root without the group would show an empty menu to users who
lack it; a root with a *broader* group would show a menu whose children are
all invisible.

### Sequence

Children are renumbered 10–50 in reading order: read mail, review AI triage,
configure, manage rules, inspect status. The root stays at 90 under Discuss
so it sorts after Odoo's own Discuss entries rather than above them.

## Migration of existing installs

`ir.ui.menu` records are updated by xmlid on module upgrade, so the
reparenting applies to existing databases without a migration script. The
only manual step is clearing the menu cache — Odoo does this on upgrade.

No `ir.model.data` changes: no xmlid is renamed, created or deleted.

## Risks and how they are handled

| Risk | Handling |
|---|---|
| Empty "Inställningar" left behind | The record *is* the root — renamed, not orphaned. Verified by asserting no menu named "Inställningar" under Discuss. |
| Broken `parent=` references | xmlid unchanged; the three modules' declarations keep resolving. |
| Users without the group see an empty root | Root carries the same group as its children. |
| Bookmarks to old menu URLs | Menu ids unchanged; only parent and name change. |
| Two menus reading as "settings" | "Inställningar" is gone; "E-postkonfiguration" is a child, not a sibling of Odoo's Configuration. |

## Testing

Manual, in `luke18a`:

1. Discuss shows exactly one "E-post" entry.
2. No menu named "Inställningar" under Discuss.
3. All five children present, in the intended order.
4. A `server` rule and a `client` rule both appear in Regler.
5. An inactive rule appears in Regler.
6. Sieve-status shows `last_error` for a failed sync.
7. E-postkonfiguration opens the logged-in user's own form, editable.
8. A user without `group_own_email_settings` does not see the root.
