# Mail menu structure

## ADDED Requirements

### Requirement: Mail settings live under Discuss Configuration
The system SHALL place the mail settings entries under Odoo's existing
Discuss Configuration menu (`mail.menu_configuration`), and SHALL NOT
define a separate configuration root under Discuss.

#### Scenario: Settings appear beside Odoo's own
- **GIVEN** the mail modules are installed
- **WHEN** a user opens Discuss → Konfiguration
- **THEN** E-postinställningar and E-postregler are listed after
  Notifications, Voice & Video and Canned Responses

#### Scenario: No separate settings root
- **GIVEN** the previous structure had a root named "Inställningar"
- **WHEN** a user opens Discuss
- **THEN** no menu named "Inställningar" is shown

#### Scenario: Odoo's configuration menu is untouched
- **GIVEN** `mail.menu_configuration` displays as "Konfiguration"
- **WHEN** the change is applied
- **THEN** its name, parent and sequence are unchanged
- **AND** its three original children remain

### Requirement: Mail reading stays top-level
The system SHALL keep Imap-mail and Mail-hjälpredan as top-level entries
under Discuss, and SHALL NOT move them into a configuration submenu.

#### Scenario: Daily mail work is one click away
- **GIVEN** the mail modules are installed
- **WHEN** a user opens Discuss
- **THEN** Imap-mail is a direct child of Discuss
- **AND** Mail-hjälpredan is a direct child of Discuss

### Requirement: Own email settings opens the own user
The system SHALL open the logged-in user's own `res.users` form on the
"E-mail settings" tab from the E-postinställningar menu.

#### Scenario: Opens own record
- **GIVEN** a user without permission to read other users
- **WHEN** the user opens E-postinställningar
- **THEN** the form shows the logged-in user's own record
- **AND** no access error is raised

#### Scenario: Editable on open
- **GIVEN** the user opens E-postinställningar
- **THEN** the form opens in edit mode

### Requirement: One rule list for both enforcement modes
The system SHALL present all `user_mail_ai.rule` records for the user in a
single list, regardless of `enforcement`, and SHALL NOT provide a second
menu that presents rules.

#### Scenario: Server rule visible in the rule list
- **GIVEN** a rule with `enforcement = 'server'`
- **WHEN** the user opens the E-postregler menu
- **THEN** the rule is listed

#### Scenario: Client rule visible in the same list
- **GIVEN** a rule with `enforcement = 'client'`
- **WHEN** the user opens the E-postregler menu
- **THEN** the rule is listed

#### Scenario: Inactive rules are listed
- **GIVEN** a rule with `active = False`
- **WHEN** the user opens the E-postregler menu
- **THEN** the rule is listed

#### Scenario: Other users' rules are not listed
- **GIVEN** a rule belonging to another user
- **WHEN** the user opens the E-postregler menu
- **THEN** the rule is not listed

### Requirement: Sieve script status is not a rule list
The system SHALL NOT present the generated `sieve.script` as a menu entry
beside the rule list, and SHALL make it reachable from the mail settings
page instead.

#### Scenario: No second rule-like entry
- **GIVEN** Discuss → Konfiguration is open
- **WHEN** the user looks at its children
- **THEN** no entry named as a rule list for server rules is present

#### Scenario: Failed sync is still visible
- **GIVEN** a script with `state = 'error'`
- **WHEN** the user opens the mail settings page
- **THEN** a control leads to the script view
- **AND** `last_error` is displayed there

### Requirement: Settings entries respect the email settings group
The system SHALL restrict the mail settings entries to users holding
`user_mail_common.group_own_email_settings`.

#### Scenario: User with the group sees the entries
- **GIVEN** a user in `group_own_email_settings`
- **WHEN** the user opens Discuss → Konfiguration
- **THEN** E-postinställningar and E-postregler are shown

#### Scenario: User without the group does not
- **GIVEN** a user not in `group_own_email_settings`
- **WHEN** the user opens Discuss → Konfiguration
- **THEN** E-postinställningar and E-postregler are not shown
- **AND** Odoo's own three entries are still shown
