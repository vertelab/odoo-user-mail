# mail-menus Specification

## ADDED Requirements

### Requirement: Single mail root menu
The system SHALL present all mail features under one root menu named
"E-post" under Discuss, and SHALL NOT define more than one top-level mail
menu.

#### Scenario: One entry at the top level
- **GIVEN** the mail modules are installed
- **WHEN** a user opens Discuss
- **THEN** exactly one menu entry named "E-post" is shown for mail
- **AND** it contains Imap-mail, Mail-hjälpredan, E-postkonfiguration,
  Regler and Sieve-status as children

#### Scenario: No empty leftover root
- **GIVEN** the previous structure had a root named "Inställningar"
- **WHEN** the change is applied
- **THEN** no menu named "Inställningar" remains under Discuss
- **AND** no menu is left without children

### Requirement: No name collision with Odoo Configuration
The system SHALL NOT define a Discuss menu whose name collides with
Odoo's own `mail.menu_configuration`.

#### Scenario: Configuration stays unambiguous
- **GIVEN** `mail.menu_configuration` is displayed as "Konfiguration"
- **WHEN** a user opens Discuss
- **THEN** no second menu with a name that reads as "settings" is present

### Requirement: Rules are managed in one place
The system SHALL show all `user_mail_ai.rule` records in a single menu,
regardless of `enforcement`, and SHALL NOT split rules into separate menus
by where they execute.

#### Scenario: Server rule visible in the rule list
- **GIVEN** a rule with `enforcement = 'server'`
- **WHEN** the user opens the Regler menu
- **THEN** the rule is listed
- **AND** its enforcement is shown on the rule form

#### Scenario: Client rule visible in the same list
- **GIVEN** a rule with `enforcement = 'client'`
- **WHEN** the user opens the Regler menu
- **THEN** the rule is listed alongside server rules

#### Scenario: Inactive rules are listed
- **GIVEN** a rule with `active = False`
- **WHEN** the user opens the Regler menu
- **THEN** the rule is listed
- **AND** is visually distinguishable as inactive

### Requirement: Sieve script status is not a rule list
The system SHALL present the generated `sieve.script` as a status view,
named so that it cannot be mistaken for a second rule list.

#### Scenario: Menu name states status
- **GIVEN** the generated script view
- **WHEN** the user opens the menu
- **THEN** the menu name identifies it as status, not as rule management

#### Scenario: Failed sync is visible
- **GIVEN** a script with `state = 'error'`
- **WHEN** the user opens the script view
- **THEN** `last_error` is displayed
- **AND** the view is reachable without opening a rule

### Requirement: Own email configuration opens the own user
The system SHALL open the logged-in user's own `res.users` form on the
"E-mail settings" tab from the E-postkonfiguration menu.

#### Scenario: Opens own record
- **GIVEN** a user without permission to read other users
- **WHEN** the user opens E-postkonfiguration
- **THEN** the user's own form opens
- **AND** no access error is raised

#### Scenario: Editable on open
- **GIVEN** the user opens E-postkonfiguration
- **WHEN** the form is displayed
- **THEN** the form is in edit mode
