# mail-rules Specification

## ADDED Requirements

### Requirement: Sieve script ownership
The system SHALL maintain exactly one generated Sieve script per user,
named `odoo_ai`, and SHALL never modify scripts it did not generate.

#### Scenario: Own script, foreign scripts untouched
- **GIVEN** a user with a hand-written ManageSieve script named `arkiv`
- **WHEN** Odoo syncs its generated script
- **THEN** write only the script named `odoo_ai`
- **AND** leave `arkiv` byte-for-byte unchanged

#### Scenario: Script is regenerated, never patched
- **GIVEN** a user with three server rules
- **WHEN** one rule is edited
- **THEN** regenerate the entire script from the rule set
- **AND** not merge into the previous body

### Requirement: Validation before activation
The system SHALL validate a generated script both locally and on the server
before activating it, and SHALL NOT activate a script that fails either.

#### Scenario: Local parse fails
- **GIVEN** a generated script that `sievelib.parser` cannot parse
- **WHEN** sync runs
- **THEN** abort the sync
- **AND** leave the previously active script in place
- **AND** record the error on `sieve.script`

#### Scenario: Server rejects the script
- **GIVEN** a script that parses locally but `checkscript` rejects
- **WHEN** sync runs
- **THEN** abort before `putscript`
- **AND** store the server's `errmsg` in `last_error`

### Requirement: Sync failures are visible
The system SHALL record sync state and error text, and SHALL surface them
to the user rather than failing silently.

#### Scenario: ManageSieve unreachable
- **GIVEN** the ManageSieve port is not answering
- **WHEN** the daily cron runs
- **THEN** set `state='error'` and populate `last_error`
- **AND** not raise past the cron
- **AND** show the error in the user interface

### Requirement: Vacation is per-user
The system SHALL compile a user's vacation autoresponder into that user's
own script, and SHALL NOT write vacation into a shared or global script.

#### Scenario: Vacation never reaches a global script
- **GIVEN** a user with `vacation_active` set
- **WHEN** the vacation block is compiled
- **THEN** write it to the user's own script
- **AND** never to `default.sieve` or any file shared between users

#### Scenario: Sender address is the user's own
- **GIVEN** a user with vacation active
- **WHEN** the vacation action is compiled
- **THEN** emit `vacation :from "<the user's own address>"`
- **AND** not rely on the postmaster default

### Requirement: Autoresponder loop protection
The system SHALL limit autoresponses so that a sender receives at most one
reply per period, and SHALL NOT combine an autoresponder with an
unlimited redirect in the same rule.

#### Scenario: Repeated mail from one sender
- **GIVEN** vacation active for a user
- **WHEN** the same sender sends several messages within the period
- **THEN** emit `vacation :days <n>` with a positive day count
- **AND** send at most one reply per sender per period

#### Scenario: No redirect inside vacation
- **GIVEN** a user with `vacation_forward` populated
- **WHEN** the vacation block is compiled
- **THEN** do not emit `redirect`
- **AND** leave forwarding to the separate `forward_active` mechanism

### Requirement: Vacation date range
The system SHALL activate the vacation autoresponder only between
`vacation_from` and `vacation_to`, evaluated daily, and SHALL remove the
block outside that range.

#### Scenario: Inside the range
- **GIVEN** `vacation_active` set and today between `vacation_from` and `vacation_to`
- **WHEN** the daily cron runs
- **THEN** the user's script contains the vacation block

#### Scenario: Outside the range
- **GIVEN** `vacation_active` set and today after `vacation_to`
- **WHEN** the daily cron runs
- **THEN** the vacation block is removed from the script

#### Scenario: Switch off
- **GIVEN** `vacation_active` unset
- **WHEN** the user saves
- **THEN** the vacation block is removed immediately
- **AND** no autoresponse is sent

### Requirement: Rule execution point
The system SHALL record for each rule whether it is enforced in Odoo or on
the server, and SHALL apply a rule in exactly one place.

#### Scenario: Server rule is not applied twice
- **GIVEN** a rule with `enforcement='server'`
- **WHEN** the poller processes a matching message
- **THEN** skip that rule in the Odoo-side rule application
- **AND** let the server's Sieve script handle it

#### Scenario: Unsupported action on the server
- **GIVEN** a rule with `enforcement='server'` and an action Sieve cannot express
- **WHEN** the rule is saved
- **THEN** raise a validation error naming the action
- **AND** not silently downgrade the rule to client-side

### Requirement: Mailbox name quoting
The system SHALL emit folder names with exactly one level of quoting, so
that folders containing spaces resolve correctly.

#### Scenario: Folder with a space
- **GIVEN** a rule moving mail to `INBOX.Linkedin mm`
- **WHEN** the script is compiled
- **THEN** emit `fileinto :create "INBOX.Linkedin mm"`
- **AND** not emit a double-escaped name

### Requirement: Rule creation from a message
The system SHALL let a user create a rule from a selected message, with
conditions pre-filled from that message.

#### Scenario: Pre-fill from sender
- **GIVEN** a message selected in the mail client
- **WHEN** the user opens the rule dialog
- **THEN** pre-fill the sender condition from the message's `From`
- **AND** preselect server-side enforcement
- **AND** offer a folder picker populated from the user's mailboxes
