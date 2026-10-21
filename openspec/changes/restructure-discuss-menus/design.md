# Design: Add mail settings to Discuss → Configuration

## Current state (verified in luke18a, 2026-10-21)

Odoo's own Discuss configuration menu:

```
mail.menu_configuration (72, seq 1)  "Configuration" / "Konfiguration"
├── mail.menu_notification_settings (73, seq 1)   "Notifications"
├── mail.menu_call_settings         (74, seq 5)   "Voice & Video"
└── mail.menu_canned_responses      (75, seq 15)  "Canned Responses"
```

No group restrictions — every internal user sees it.

Our menus:

```
mail.menu_root_discuss (71)
├── user_mail_common.menu_user_mail_settings (512, seq 90)  "Inställningar"
│   ├── user_mail_client.menu_user_mail_own_settings (513, seq 10) "E-postkonfiguration"
│   ├── user_mail_ai.menu_user_mail_ai_rules         (549, seq 20) "Regler"
│   └── user_mail_common.menu_sieve_script           (551, seq 30) "Serverregler (Sieve)"
├── user_mail_imap.menu_user_mail_imap (514, seq 99)  "Imap-mail"
└── user_mail_ai.menu_user_mail_ai     (548, seq 100) "Mail-hjälpredan"
```

## Target

```
mail.menu_root_discuss
├── mail.menu_configuration (72)
│   ├── mail.menu_notification_settings (seq 1)
│   ├── mail.menu_call_settings         (seq 5)
│   ├── mail.menu_canned_responses      (seq 15)
│   ├── user_mail_client.menu_user_mail_own_settings (seq 20) "E-postinställningar"
│   └── user_mail_ai.menu_user_mail_ai_rules         (seq 30) "E-postregler"
├── user_mail_imap.menu_user_mail_imap (seq 99)  "Imap-mail"       ← unchanged
└── user_mail_ai.menu_user_mail_ai     (seq 100) "Mail-hjälpredan" ← unchanged
```

## Decisions

### Reuse Odoo's Configuration menu, do not build a fourth root

`mail.menu_configuration` already exists and already holds Discuss settings.
Adding a parallel root named "Konfiguration" would recreate the collision this
change removes. Parenting to the existing menu costs one field and adds no
dependency — `user_mail_common` already depends on `mail`.

### Imap-mail and Mail-hjälpredan stay top-level

Reading mail should not require opening a settings folder. Only settings move.

### The "Inställningar" root is deleted, not renamed

Once its children move, the root has no children. An empty menu under Discuss
is noise.

Deletion must happen **after** the children are reparented, and it must use
`<delete>` on an xmlid that exists. Odoo 18 crashes on `<delete>` against a
missing xmlid, so the order in the XML file matters:

```xml
<!-- 1. reparent the children first -->
<record id="menu_user_mail_own_settings" model="ir.ui.menu">
    <field name="parent_id" ref="mail.menu_configuration"/>
    <field name="sequence">20</field>
</record>
<record id="menu_user_mail_ai_rules" model="ir.ui.menu">
    <field name="parent_id" ref="mail.menu_configuration"/>
    <field name="sequence">30</field>
</record>

<!-- 2. then delete the now-empty root -->
<delete id="menu_user_mail_settings" model="ir.ui.menu"/>
```

The two child records live in different modules (`user_mail_client`,
`user_mail_ai`), so the reparenting must happen in each module's own XML —
`user_mail_common` cannot rewrite another module's record without taking on a
dependency on it. The `<delete>` belongs in `user_mail_common`, which owns the
root, and must run after both.

**Module load order is therefore load-bearing:** `user_mail_common` loads
first (both others depend on it), so a `<delete>` there would run *before* the
reparenting. The delete must instead live in the module that loads last, or be
guarded.

**Simpler and safer: do not delete the root in XML at all.** Set it
`active = False`:

```xml
<record id="menu_user_mail_settings" model="ir.ui.menu">
    <field name="active" eval="False"/>
</record>
```

An inactive menu is invisible in the UI, the record survives, and no ordering
constraint exists. This is the chosen approach.

### "Serverregler (Sieve)" leaves the menu

It is `sieve.script`: generated body, sync state, `last_error`. Sitting next to
"E-postregler" it implies a second rule system.

The view is not deleted — it moves to a button on the E-postinställningar
page. That page is where a user who asks "are my rules actually running?" is
already looking.

**This is the one change that can lose information if done alone.** Removing
the menu entry without adding the button would make a failed sync invisible in
the UI. Both must ship together.

The button is an `ir.actions.act_window` on `sieve.script` with
`domain = [('user_id', '=', uid)]`, placed in the form's header or as a
stat button. The existing `sieve_script_action` can be reused.

### "Regler" → "E-postregler" needs no action change

`user_mail_ai_rule_action` already has:
- `domain = [('user_id', '=', uid)]`
- `context = {'active_test': False}`

No `enforcement` filter — it shows both kinds today. Only the label changes.

### "E-postkonfiguration" → "E-postinställningar"

Same `ir.actions.server` returning an act_window with `res_id = env.uid`.
`ir.actions.act_window.res_id` is a static integer and cannot express "the
logged-in user"; an act_window without `res_id` opens a list where a normal
user gets an access error.

The URL `/odoo/settings/1/users/25` is the *admin* path to one specific user.
The menu must resolve to `env.uid` so each user lands on their own record.

### Groups

`mail.menu_configuration` has no groups. Our two entries must carry
`user_mail_common.group_own_email_settings` so users who cannot use them do not
see entries that fail on click.

## Migration

`ir.ui.menu` records are updated by xmlid on module upgrade, so existing
databases get the new parents and names without a migration script. No
`ir.model.data` changes: no xmlid is created, renamed or deleted.

## Risks

| Risk | Handling |
|---|---|
| Failed sync becomes invisible | The status button on E-postinställningar ships in the same change. |
| Delete ordering across modules | Avoided entirely — the root is deactivated, not deleted. |
| Users without the group see entries that fail | Both entries carry the group. |
| Bookmarks | Menu ids unchanged; only names, parents and one `active` flag. |
| Odoo's menu renamed by an upgrade | We never touch `mail.menu_configuration`; only add children. |

## Testing

Manual, in `luke18a`:

1. Discuss → Konfiguration shows five children: Notifications, Voice & Video,
   Canned Responses, E-postinställningar, E-postregler.
2. No "Inställningar" root remains under Discuss.
3. Imap-mail and Mail-hjälpredan are still direct children of Discuss.
4. No "Serverregler (Sieve)" entry remains.
5. A `server` rule and a `client` rule both appear in E-postregler.
6. E-postinställningar opens the logged-in user's own form, editable.
7. The Sieve-status button opens the script view and shows `last_error` on a
   failed sync.
8. A user without `group_own_email_settings` sees Odoo's three entries but not
   ours.
