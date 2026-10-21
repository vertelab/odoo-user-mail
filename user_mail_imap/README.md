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

## Flaggor, etiketter och oläst

Tre saker som ser besläktade ut men är olika axlar:

**1. Stjärnan (`flagged`)** är en IMAP-systemflagga (`\Flagged`).

**2. Etiketterna** är IMAP-nyckelord och sätts från menyn bredvid stjärnan
uppe i meddelandevyn: `important`, `spam`, `todo`, `personal`, `work`.
Definitionerna bor i `static/src/js/mail_flags.esm.js` och importeras av
**både** listans filter och meddelandets etikettmeny — annars kan en etikett
bli sättbar men ofiltrerbar, eller tvärtom.

`important` skrivs som nyckelordet `Important`. Äldre mail som markerades
med `\Answered` (när `important` var kopplat till svarsflödet) läses
fortfarande som `important`, men nya skrivs aldrig så — svarsflödet äger
`\Answered`.

**3. Oläst är ingen etikett.** Det är en egen axel som mappar till IMAP:s
`UNSEEN`, och den har en egen knapp i listan (inte en sjunde post i
flaggmenyn). Skälet är att `UNSEEN` är serverindexerat och snabbast, och att
en "oläst"-etikett hade skapat två vägar till samma serverfält — plus
erbjudit oläst som något man *sätter*.

### Filtrering sker på servern

Både flagg- och olästfiltret går mot **hela mappen** via IMAP `SEARCH`, inte
mot de ~80 rader som råkar vara laddade. Det var buggen: ett stjärnmärkt
mail på plats 412 svarade "Inga mail med den flaggan i mappen" eftersom
klienten filtrerade en ofullständig sida.

- `action_filter_mails(folder, flag, unread, offset, limit)` — ny metod.
- `_flag_criteria(flag, unread)` bygger `FLAGGED` / `KEYWORD "<x>"` /
  `UNSEEN`. Kriterierna läggs som **AND-led utanför** sökningens
  `OR`-träd: IMAP:s `OR` tar exakt två nycklar, så ett tredje led inuti
  hade brutit uttrycket.
- `/imap/filter` är en egen rutt. Ett filter utan sökord är ett filter, inte
  en sökning; att tvinga `query=''` genom sökvägen fick ett tomt sökfält att
  se ut som att det rensade filtret.
- Klienten anropar alltid `applyView({query, flag, unread, offset})` — en
  gemensam lastväg. Delade anrop kunde inte veta om det andra filtret var
  aktivt, så `total` blev fel och pagineringen hoppade.

### Okänd status gissas aldrig

Rader från OKF-sökningen får sin flagg-/lässtatus via ett batchat
`UID FETCH (FLAGS)` (`_fetch_flag_status`). Misslyckas det blir `seen` och
`flagged` **`None`** — inte `False`. Att gissa oläst hade gett fetstil på
lästa mail och fått dem att fastna i olästfiltret. Okänd status utesluts ur
olästfiltret i stället för att räknas dit.

### Ett öppnat mail laddar inte om listan

Att öppna ett mail markerar det läst på servern. Listan laddas därför inte
om (R4): mitt i läsningen hade raden försvunnit ur ett aktivt olästfilter.
Radens `seen` uppdateras på plats så att fetstilen släpper direkt.

## Kända testfall i `tests/test_imap.py`

Nio tester i IMAP-sviten faller på en ren `18.0`-kodbas utan ändringar
(fetch/search-mockar och anrop mot riktiga servrar). De är **inte** relaterade
till E-postinställningar-formen — verifierat genom att köra sviten på en
ostädad checkout: samma 9 fel. Jämför alltid mot den baslinjen innan du
misstänker en regression.
