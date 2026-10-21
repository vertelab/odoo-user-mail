# User Mail Client

Klientdelen av e-postkonfigurationen: de två ytor där en användare ser och
ändrar sina egna mailinställningar.

## Två ytor, olika syften

| Yta | Vad den är | När den används |
|---|---|---|
| **E-postinställningar** (menyn, Discuss → Konfiguration) | Fristående `res.users`-form, `view_user_mail_own_settings_form` | Fokus på mail. Namn överst, sedan mailfälten. Inga flikar. |
| **Min profil → fliken E-postinställningar** | `view_users_form_simple_modif_mail`, som ärver `base.view_users_form_simple_modif` | När användaren redan är i profildialogen. Har profildialogens flikar. |

Den fristående formen finns därför att den ärvda vyn drar in **hela**
profildialogen — alla flikar — och dessutom filtrerar sin arch mot
`SELF_READABLE_FIELDS`/`SELF_WRITEABLE_FIELDS`, vilket gör att mailfält som
inte står i de listorna renderas som tomma grupper. En egen vy utan
`inherit_id` slipper båda problemen.

Menyn går via server-actionen `action_user_mail_own_settings`, som alltid
öppnar den inloggade användarens egen post (`res_id = env.uid`) och är
begränsad till gruppen `group_own_email_settings`.

## Lösenordet byts i en wizard — inte i formen

Det finns **inget lösenordsfält** på formen, med flit. Lösenordet sätts via
guiden `user.mail.imap.password.wizard` (knappen *Ange mail-lösenord*), som
anropar `action_set_imap_password()` och där verifierar lösenordet innan det
sparas. Ett rått fält skulle kringgå den verifieringen.

Två saker att känna till:

- **Lösenordet skrivs aldrig ut igen.** Det lagras Fernet-krypterat och fältet
  är write-only i praktiken — formen visar bara om ett lösenord finns.
- **Att byta mailösenord ändrar inte Odoo-inloggningen** i den här formen.
  Kontraktet "Odoo-lösenord == mail-lösenord" upprätthålls av
  `mail-credentials`-specen när lösenordet sätts den vägen; guiden här sätter
  bara mailkopian. Är du osäker på vilket lösenord som gäller — se
  `user_mail_imap/README.md`.

## Skrivrättigheter (viktigt vid felsökning)

`base.group_user` har **bara läsrätt** på `res.users`. Skrivning på den egna
posten fungerar ändå, via två saker som hänger ihop:

1. Mailfälten står i `SELF_WRITEABLE_FIELDS` (`user_mail_common`), vilket får
   `base.write()` att skriva som superuser.
2. Den genvägen **prövar inte grupptillhörighet**. Därför finns en explicit
   grind, `_check_mail_settings_rights()`, som nekar self-write av mailfälten
   utan `group_own_email_settings` (och släpper igenom `group_erp_manager`).

Fält som hör till servern eller admin är medvetet **inte** självskrivbara:
`postfix_active`, `postfix_mail`, `maildir`, `quota`, `dovecot_password`.

## Tester

```bash
# på en testdatabas, inte ledningssystem
odoo --config /etc/odoo/odoo.conf -d <testdb> --init=user_mail_client \
     --test-enable --test-tags=/user_mail_client --stop-after-init \
     --workers=0 --http-port=4491 --without-demo=all
```

Använd `odoo` direkt, inte `checkmodule`, på en färsk databas: `checkmodule`s
AGE-init skapar ett tomt `ag_catalog` som sedan fäller `ag_label`.
