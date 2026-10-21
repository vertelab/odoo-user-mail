# User Mail: IMAP Client

IMAP-klienten med per-användare-pollning, plus lösenordshanteringen för
mailkontot.

## Lösenordskontraktet (oförändrat)

**Odoo-lösenord == mail-lösenord.** Det är avsiktligt och gäller fortfarande
efter att den fristående E-postinställningar-formen infördes:

- Lösenordet verifieras mot `dovecot_password` (`sha512_crypt`).
- Det lagras Fernet-krypterat i `imap_password`; klartext persisteras aldrig.
- Fältet är write-only — det läses aldrig tillbaka till UI:t.
- Lösenordet sätts alltid via `user.mail.imap.password.wizard` →
  `action_set_imap_password()`. Ingen yta skriver `imap_password` direkt.

Se `mail-credentials`-specen för det fullständiga kontraktet.

## Två ytor där lösenordet nås

Samma lösenordssektion renderas på båda ställena:

1. **Min profil → fliken E-postinställningar** —
   `view_users_form_simple_modif_imap` (i `views/res_users_view.xml`).
2. **Menyn E-postinställningar** — `view_user_mail_own_settings_form_imap`
   (i `views/own_settings/res_users_view.xml`), som ärver den fristående
   formen från `user_mail_client`.

Den andra vyn fyller en markör, `<div name="mail_credentials_anchor"/>`, som
`user_mail_client` lämnar i sin form. Det är därför `user_mail_client` inte
behöver känna till IMAP.

## Varför `user_mail_client` inte står i `depends`

Beroenderiktningen i repot är `client → common` och `imap → common`; aldrig
`imap → client`. Vyn i `views/own_settings/` refererar xmlid:t
`user_mail_client.view_user_mail_own_settings_form`, och den referensen löses
vid installationstillfället — modulerna installeras ihop.

**Konsekvens:** `user_mail_imap` kan inte installeras ensam i en databas där
`user_mail_client` saknas. Det är känt och accepterat (de driftsätts som ett
paket). Vid testkörning mot en färsk databas måste båda initieras:

```bash
odoo --config /etc/odoo/odoo.conf -d <testdb> \
     --init=user_mail_client,user_mail_imap \
     --test-enable --test-tags=/user_mail_imap --stop-after-init \
     --workers=0 --http-port=4492 --without-demo=all
```

## Kända testfall i `tests/test_imap.py`

Nio tester i IMAP-sviten faller på en ren `18.0`-kodbas utan ändringar
(fetch/search-mockar och anrop mot riktiga servrar). De är **inte** relaterade
till E-postinställningar-formen — verifierat genom att köra sviten på en
ostädad checkout: samma 9 fel. Jämför alltid mot den baslinjen innan du
misstänker en regression.
