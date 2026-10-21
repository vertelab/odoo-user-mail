# Tasks: Add mail settings to Discuss → Configuration

All work is local to `luke18a`. Deployment is **not** a task in this change —
it happens only after explicit approval.

## 1. Verify the current state

- [x] 1.1 Confirm `mail.menu_configuration` id, name, sequence and children
      (Notifications 1, Voice & Video 5, Canned Responses 15) in `luke18a`.
- [x] 1.2 Confirm `mail.menu_configuration` has no group restrictions.
- [x] 1.3 Confirm `user_mail_client` and `user_mail_ai` both depend on `mail`
      (directly or transitively) so parenting to `mail.menu_configuration`
      adds no new dependency.
- [x] 1.4 Record the current menu tree of all `user_mail*` menus as the
      before-state.

## 2. Move E-postinställningar

- [x] 2.1 In `user_mail_client/views/menus_views.xml`, set
      `parent_id` to `mail.menu_configuration` and `sequence` to 20 on
      `menu_user_mail_own_settings`.
- [x] 2.2 Rename the menu to "E-postinställningar".
- [x] 2.3 Add `groups="user_mail_common.group_own_email_settings"` to the
      menu.
- [x] 2.4 Verify the action still resolves to `env.uid` — an act_window
      without `res_id` would open a list and fail for a non-admin.

## 3. Move and rename E-postregler

- [x] 3.1 In `user_mail_ai/views/user_mail_ai_rule_views.xml`, set
      `parent_id` to `mail.menu_configuration` and `sequence` to 30 on
      `menu_user_mail_ai_rules`.
- [x] 3.2 Rename the menu to "E-postregler".
- [x] 3.3 Add `groups="user_mail_common.group_own_email_settings"`.
- [x] 3.4 Verify `user_mail_ai_rule_action` still has no `enforcement`
      filter and keeps `active_test: False`.

## 4. Retire the "Inställningar" root

- [x] 4.1 In `user_mail_common/views/menus_views.xml`, set
      `active = False` on `menu_user_mail_settings`.
- [x] 4.2 Do **not** use `<delete>` — `user_mail_common` loads before the
      two modules that reparent their children, so a delete would run first
      and orphan them.
- [x] 4.3 Verify the root is gone from the UI and no child is orphaned.

## 5. Move Sieve status to the settings page

- [x] 5.1 Add a "Sieve-status" control on the E-postinställningar page
      (button or stat button) opening `sieve_script_action`.
- [x] 5.2 Remove `menu_sieve_script` from the menu tree in
      `user_mail_common/views/sieve_script_views.xml` (deactivate, do not
      delete).
- [x] 5.3 Verify the script view is still reachable via the button and that
      `last_error` is visible on a failed sync.
- [x] 5.4 Confirm the existing red banner in the "E-mail settings" tab still
      appears on `sieve_script_state == 'error'`.

## 6. Upgrade and verify

- [x] 6.1 Stop `odoo`, upgrade `user_mail_common`, `user_mail_client`,
      `user_mail_ai` with `-u`, start `odoo`.
- [x] 6.2 Check the log for errors from this change.
- [x] 6.3 Verify the menu tree matches the design: Discuss → Konfiguration
      with five children in the right order.
- [x] 6.4 Verify no "Inställningar" root and no "Serverregler (Sieve)" entry.
- [x] 6.5 Verify Imap-mail and Mail-hjälpredan are still direct children of
      Discuss.
- [x] 6.6 Log in as a user in `group_own_email_settings` and confirm both
      entries open correctly.
- [x] 6.7 Log in as a user **without** the group and confirm our two entries
      are hidden while Odoo's three are shown.
- [x] 6.8 Create one `server` rule and one `client` rule; confirm both appear
      in E-postregler.

## 7. Documentation

- [x] 7.1 Update `openspec/config.yaml` if the module map or conventions
      changed.
- [x] 7.2 Run `openspec validate restructure-discuss-menus`.
