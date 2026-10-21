# User Mail: AI Assistant

Personlig AI-mailhjälpreda — IMAP-triage, Odoo Mind (graf), Teams→kalender.

## Vad som OKF-indexeras

`user_mail_ai.mail` är den modell som driver sökfältet i mailklienten. Den
registrerar sig både för dirty-indexering och som **sökdrivande** modell:
den garanteras en andel av varje indexeringskörning, så en stor bulk-kö
(t.ex. ett arkiv med tiotusentals poster) kan inte svälta ut den.

## `mail.message` indexeras inte längre

`mail.message` var registrerad för dirty-indexering och stod i drift för
**83 959 av 108 378** köade poster — 77,5 % av hela kön — utan att mata
någon användarsynlig sökning. Sökfältet läser `user_mail_ai.mail`, som har
sin egen registrering, och den företagsägda grenen av `mail.message`
producerade noll koncept i drift (alla 40 mail-nycklade koncept är
användarägda).

Modellen behåller `ai.okf.mixin` — fälten finns kvar och historiska rader
rörs inte. Det är bara registreringen som är borttagen:
`_okf_dirty_fields()` returnerar en tom mängd och `_register_hook()` är
borta.

**Konsekvens:** gamla `mail.message`-koncept uppdateras inte längre. Skulle
något framöver behöva dem går de att registrera om — men kontrollera först
att en konsument faktiskt läser dem, annars är det samma fälla igen.

## Mail-hjälpredans meny

Menyvalet skapas inte av modulen. En `<record>` utan `name` kraschade
registerladdningen i en färsk databas (`NOT NULL` på `ir_ui_menu.name`) —
i drift överlevde raden, så kraschen var osynlig där.
