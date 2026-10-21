# Tasks: Restructure the Discuss mail menus

Deployment is **not** a task here. It is a separate decision after review.

## Phase 1 — Root menu (`user_mail_common`)

- [ ] 1.1 In `views/menus_views.xml`: convert `menu_user_mail_settings`
      from `<menuitem>` to an `<record model="ir.ui.menu">` that renames it
      to "E-post", keeps `parent_id = mail.menu_root_discuss`, keeps
      `sequence = 90` and keeps
      `groups = user_mail_common.group_own_email_settings`.
      Keep the xmlid — three modules reference it as `parent=`.
- [ ] 1.2 Update the comment block above the record: it currently explains
      why the root exists and why the name "Inställningar" was chosen. The
      name is now "E-post" and the collision with
      `mail.menu_configuration` is gone — the reasoning must match the code.

## Phase 2 — Children renumbered and reparented

- [ ] 2.1 `user_mail_imap/views/menus_views.xml`: parent stays
      `user_mail_common.menu_user_mail_settings`, sequence `99` → `10`.
- [ ] 2.2 `user_mail_ai/views/user_mail_ai_mail_views.xml`: parent
      `mail.menu_root_discuss` → `user_mail_common.menu_user_mail_settings`,
      sequence `100` → `20`.
- [ ] 2.3 `user_mail_client/views/menus_views.xml`: sequence `10` → `30`.
- [ ] 2.4 `user_mail_ai/views/user_mail_ai_rule_views.xml`: sequence `20` → `40`.
- [ ] 2.5 `user_mail_common/views/sieve_script_views.xml`: rename
      "Serverregler (Sieve)" → "Sieve-status", sequence `30` → `50`.
      Update the comment to say why it is a status view and not a rule list.

## Phase 3 — Verify the rule list shows both enforcements

- [ ] 3.1 Confirm `user_mail_ai_rule_action` has no `enforcement` filter
      in its domain (it should not — only `user_id` and `active_test`).
- [ ] 3.2 Confirm the rule form shows `enforcement` (added in
      `add-sieve-rules`), so the distinction is visible inside a rule.

## Phase 4 — Verification

- [ ] 4.1 `python3 -m py_compile` on every touched `.py` file (manifests).
- [ ] 4.2 Parse every touched XML file.
- [ ] 4.3 Upgrade `user_mail_common`, `user_mail_imap`, `user_mail_ai`,
      `user_mail_client` in `luke18a` with no errors from this code.
- [ ] 4.4 Query `ir_ui_menu` and assert the resulting tree matches the
      design: one root named "E-post", five children in order, no menu
      named "Inställningar" under Discuss.
- [ ] 4.5 Confirm all `parent=` xmlid references still resolve (no
      `ir.model.data` errors during upgrade).

## Manual test plan

1. **One root:** Discuss shows exactly one "E-post" entry; Imap-mail,
   Mail-hjälpredan and the settings entries are no longer siblings of it.
2. **No collision:** no menu named "Inställningar" under Discuss; Odoo's
   own "Konfiguration" is unambiguous.
3. **Order:** children appear as Imap-mail, Mail-hjälpredan,
   E-postkonfiguration, Regler, Sieve-status.
4. **Both enforcements in Regler:** create one `server` rule and one
   `client` rule; both appear in the same list.
5. **Inactive visible:** deactivate a rule; it still appears.
6. **Sieve-status:** with a failed sync, `last_error` is shown and the
   view is reachable without opening a rule.
7. **Own form:** E-postkonfiguration opens the logged-in user's own form,
   in edit mode, on the "E-mail settings" tab.
8. **Group isolation:** a user without
   `user_mail_common.group_own_email_settings` does not see "E-post".
9. **Bookmarks:** an old bookmark to a menu action still opens it (menu
   ids unchanged).
