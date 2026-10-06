```
INSTALL INSTRUCTIONS

Installing user_mail_client will make the clients update server when changes occur to users or companies,
intall the user_mail_server on the main server database to make it recieve updates from clients.

Note that user_mail_common contains fields and functions that both user_mail_client and user_mail_server share and both the modules depend on user_mail_common.

The intended purpose user_mail modules is only for dovecot/postfix. Not for regular Odoo usage.

Install order:
Update config according to below description
Install user_mail_server on the server
Install user_mail_client on the client(s)
Set domain in settings/general settings/company/<your company> - This will trigger a sync to the server and create a catch_all for the company.
For all Users check box postfix active and use action/syncronize e-mail settings - This will sync user to the server.

-------/etc/odoo/odoo.conf-------

[options]
; This is the configuration that allows user_mail module to operate:

passwd_server = http://<your main server>:8069
passwd_dbname = <your main server database>
passwd_user = <user in passwd_dbname>
passwd_passwd = <password for passwd_user>

smtp_server = <your server for outgoing mail>
smtp_port = <your smtp port eg. 25>
smtp_encryption = <your smtp encryption eg. starttls/ssl/none>

imap_host = <your server for incoming mail>
imap_port = <your imap port eg. 993>
imap_encryption = True/False


-------/etc/postfix/main.cf-------

virtual_alias_maps = pgsql:/etc/postfix/virtual_alias_maps.cf,pgsql:/etc/postfix/email2email.cf,pgsql:/etc/postfix/virtual_forward_maps.cf,pgsql:/etc/postfix/virtual_forward_cp_maps.cf
virtual_mailbox_domains = pgsql:/etc/postfix/virtual_domains_maps.cf
virtual_mailbox_maps = pgsql:/etc/postfix/virtual_mailbox_maps.cf
virtual_mailbox_base = /var/lib/vmail/domains
virtual_transport = virtual

# Additional for quota support

virtual_create_maildirsize = yes
virtual_mailbox_extended = yes
virtual_mailbox_limit_maps = pgsql:/etc/postfix/virtual_mailbox_limit_maps.cf
virtual_mailbox_limit_override = yes
virtual_maildir_limit_message = <message>
virtual_overquota_bounce = yes

-------/etc/postfix/email2email.cf-------

user = <postgres user>
password = <postgres user password>
hosts = <main server>
dbname = <main server dbname (passwd_dbname)> 
query = SELECT postfix_mail FROM res_users WHERE postfix_mail='%s' and active = '1'  and forward_active = '0'


-------/etc/postfix/virtual_alias_maps.cf-------

user = <postgres user>
password = <postgres user password>
hosts = <main server>
dbname = <main server dbname (passwd_dbname)> 
table = postfix_alias p, res_users r 
select_field = postfix_mail 
where_field = p.mail
additional_conditions = and p.user_id = r.id and p.active = '1' 

-------/etc/postfix/virtual_domains_maps.cf-------

user = <postgres user>
password = <postgres user password>
hosts = <main server>
dbname = <main server dbname (passwd_dbname)> 
table = res_company 
select_field = domain
where_field = domain
additional_conditions = and active = '1'

-------/etc/postfix/virtual_forward_cp_maps.cf-------

user = <postgres user>
password = <postgres user password>
hosts = <main server>
dbname = <main server dbname (passwd_dbname)> 
table = res_users 
select_field = forward_address||', '||postfix_mail 
where_field = postfix_mail
additional_conditions = and forward_active = '1' and forward_cp = '1' 


-------/etc/postfix/virtual_forward_maps.cf-------

user = <postgres user>
password = <postgres user password>
hosts = <main server>
dbname = <main server dbname (passwd_dbname)> 
table = res_users 
select_field = forward_address 
where_field = postfix_mail
additional_conditions = and forward_active = '1' and forward_cp = '0' 

-------/etc/postfix/virtual_mailbox_limit_maps.cf-------

user = <postgres user>
password = <postgres user password>
hosts = <main server>
dbname = <main server dbname (passwd_dbname)> 
table = res_users  
select_field = quota
where_field = postfix_mail
additional_conditions = and postfix_active = '1'

-------/etc/postfix/virtual_mailbox_maps.cf-------

user = <postgres user>
password = <postgres user password>
hosts = <main server>
dbname = <main server dbname (passwd_dbname)> 
table = res_users  
select_field = maildir
where_field = postfix_mail 
additional_conditions = and postfix_active = '1' 

----/etc/dovecot/dovecot-sql.conf.ext

...

# Database driver: mysql, pgsql, sqlite
driver = pgsql
...
# Examples:
#   connect = host=192.168.1.1 dbname=users
#   connect = host=sql.example.com dbname=virtual user=virtual password=blarg
#   connect = /etc/dovecot/authdb.sqlite
#
connect = host=<hostname> dbname=<database> user=<postgres user> password=<postgres password>

#default_pass_scheme = MD5
default_pass_scheme = SHA512-CRYPT
#default_pass_scheme = MD5-CRYPT
#default_pass_scheme = PLAIN

# Example:
#   password_query = SELECT userid AS user, pw AS password \
#     FROM users WHERE userid = '%u' AND active = 'Y'
#
#password_query = \
#  SELECT username, domain, password \
#  FROM users WHERE username = '%n' AND domain = '%d'

password_query = SELECT postfix_mail as user, dovecot_password as password FROM res_users WHERE postfix_mail = '%u'
#password_query = SELECT user_email as user, password FROM res_users WHERE user_email = '%u'
#password_query = SELECT user_email as user, password, 'Y' as proxy FROM res_users WHERE user_email = '%u'
# Examples:
#   user_query = SELECT home, uid, gid FROM users WHERE userid = '%u'
#   user_query = SELECT dir AS home, user AS uid, group AS gid FROM users where userid = '%u'
#   user_query = SELECT home, 501 AS uid, 501 AS gid FROM users WHERE userid = '%u'
#
#user_query = \
#  SELECT home, uid, gid \
#  FROM users WHERE username = '%n' AND domain = '%d'
user_query = SELECT 5000 as uid, 5000 as gid, '/var/lib/vmail/domains/' || maildir as home, quota as userdb_quota FROM res_users WHERE postfix_mail ='%u'


# Query to get a list of all usernames.
#iterate_query = SELECT user_email AS user FROM res_users
iterate_query = SELECT postfix_mail AS user FROM res_users
```


# user_mail_ai — Mail-hjälpredan (Skiva 1–2)

Personlig AI-hjälpreda för mail. Läser IMAP via `user_mail_imap`-pollern,
arkiverar i Odoo Mind (OKF + AGE-graf), klassificerar och agerar med HITL.

## Aktivering

1. Användaren öppnar **Min profil** (avatar-menyn) → fliken *Preferences* →
   gruppen **Mail-hjälpredan** → knappen **Ange mail-lösenord**.
   Lösenordet är samma som Odoo-inloggningen och verifieras mot
   `dovecot_password` (SHA512-CRYPT) innan det sparas.
2. Bocka i **Aktivera mail-pollning** (samma grupp). Går bara när ett
   lösenord finns — annars nekas det (förhindrar felloop).
3. Valfritt: välj `ai_coworker_id` (default: Mail-hjälpredan).

Cron: User Mail IMAP Poll (var 5 min) → poller → triage → klassificering
→ Teams→calendar / promotion / utkast / routing → nudge (notis + Discuss-DM).

### Lösenordskontrakt

Odoo-lösenordet och mail-lösenordet är **samma lösenord**. När en användares
Odoo-lösenord ändras (via Min profil eller av admin) uppdateras även
`imap_password` — det loggas. `imap_password` är en **tvåvägskrypterad**
(Fernet) kopia som pollern behöver: en IMAP-*klient* måste skicka klartexten,
till skillnad från Dovecot som verifierar mot en enkelriktad hash.
Klartexten sparas aldrig.

Pollern kör bara användare som har ett `imap_password` — en användare utan
lösenord hoppas över tyst (inga fel var 5:e minut).

## Flöden (Skiva 2)

- **Promotion (objektkoppling):** mail med tråd-match (References→
  mail.message) eller LLM-kandidat → HITL `promote_mail` → godkänd →
  `mail.message` på objektets chatter (följare ser). **Default privat —
  koppling till objekt = publicering = HITL.**
- **Svarsutkast:** `reply_suggested` + intresse ≥ tröskel → LLM-utkast →
  APPEND till IMAP-Drafts (syns i Thunderbird/Roundcube/K9). Skick via
  knappen "Föreslå skick" → HITL `send_reply` → SMTP med användarens
  credentials.
- **Catchall-mail:** mail.message-hook (message_type=email, icke-intern
  avsändare) → samma triage; objekt redan känt. Svar via "Svara i tråden"
  → HITL → `message_post(parent_id=…)` i Odoo-tråden.
- **Nyhetsbrev:** första flytten → HITL `newsletter_move_rule` → godkänd →
  autonom flytt till `AI/Newsletters` (reversibel via "Flytta tillbaka").
- **Action-mail:** `\Flagged` + nudge.
- **Specialist-routing:** `user_mail_ai.routing` (kategori → coworker),
  seedad faktura → Faktura-assistenten. Bryggor lägger till fler rader.

## HITL

All HITL via `ai.coworker.hitl` (core): aktivitet i klockan, chatter,
trust-ladder (N=3 → auto-förslag). Godkända mail-HITL:ar dispatchar
promotion/skick/mapp-regel automatiskt (user_mail_ai överlagrar
`action_approve` — core förblir domän-fri).

## Konfiguration (ir.config_parameter)

- `user_mail_ai.nudge_threshold` (default 7.0) — intresse-tröskel för nudge
- `user_mail_ai.draft_threshold` (default 6.0) — tröskel för proaktivt utkast
- `user_mail_ai.max_drafts_per_cycle` (default 5)
- `user_mail_imap.drafts_folder` — fallback-mapp för utkast (annars
  LIST-detektering Drafts/Utkast)

# user_mail_ai — Skiva 3: intelligens

## Regler (user_mail_ai.rule)

Användaren styr hjälpredan med regler i klartext (meny: Imap-mail →
Mail-hjälpredan → Regler, eller smartknapp i Min profil):

- `sender`/`subject`/`category` — deterministisk matchning utan LLM.
- `llm` — fri-text-regel som utvärderas i klassificeringsprompten
  (`matched_rules` i utdata).
- Actions: ignore, block, move_to_folder, flag, nudge, draft_reply,
  send_to_specialist, create_event.
- Lägre `priority` = högre prioritet; högst prioriterad matchande regel vinner.
- Seed-defaults per användare (Teams→event, nyhetsbrev→AI/Newsletters,
  nudge-för-action) skapas vid aktivering (`_ensure_default_rules`).
- Trust-ladder standing rules (ai.coworker.hitl) importeras som rules
  med `source='trust_ladder'` (t.ex. newsletter_move_rule → move_to_folder).

## Intresseprofil (hybrid)

- `ai_profile_text` (prompt-text) + `ai_profile_embedding` (pgvector-likhet)
  genereras veckovis av cron (`_recompute_profiles`) från OKF-personligt,
  interaktionshistorik och graf-volym (graph_query).
- Klassificeringsprompten inkluderar profilen; final `interest_score` =
  viktad kombination (LLM + embedding-likhet), vikten via
  `user_mail_ai.profile_weight_llm` (default 0.7). Komponenterna sparas i
  `interest_components`.

## Digest

- Daglig morgonbrief (`ai_digest_enabled`) + veckovis djup
  (`ai_digest_weekday`) — levereras som Odoo-notis (aldrig mail, undviker
  loop) och arkiveras som OKF-koncept (frågbarhet).

## Heartbeat

- Skill "Granska öppna mail-ärenden" → coworkern anropar
  `_heartbeat_review()` (via odoo_call_method): hittar stale action-mail,
  osedda utkast, förfallna follow-ups och Reply Zero → nudge + sätter
  `follow_up_at`.

## Konfiguration (ir.config_parameter)

- `user_mail_ai.profile_weight_llm` (default 0.7)
- `user_mail_ai.nudge_threshold` / `draft_threshold` / `max_drafts_per_cycle`

# user_mail_ai — Minnessynk (mail-memory-sync)

Mail-hjälpredans minne består av tre delar: **OKF-koncept** (sökbart
arkiv), **`:MailMessage`-nod** i AGE-grafen och **`SENT_BY`-kanten** till
avsändarpartnern.

## Markör på triage-raden

- `memory_synced_at` — sätts när alla tre stegen lyckats.
- `memory_state` — `pending` / `synced` / `failed`. Ett mail vars
  arkivering kastar blir `failed` i stället för en tyst nolla; det syns
  som röd rad i triage-listvyn.

Markören är **rådgivande** — reparationen verifierar vad som faktiskt
finns i stället för att lita blint på den.

## Byggs vid ingest

`_ingest_message()` skapar noden + kanten direkt (inte via 5-min-cronen),
så grafen inte släpar efter. `cron_sync_graph` finns kvar som reparatör.

## Reparation + städning (cron)

- **Mail-AI: Reparera mail-minne** (var 15 min) — hittar mail med
  `memory_state != 'synced'` för användare med pollning aktiverad och
  bygger det som saknas. Idempotent; OKF-konceptet skapas **bara om det
  saknas** (mail är immutabla — ingen versionering). Kör `_create_edges`
  om så kanter till sena partner-noder läks. Bounded batch (50/varv).
- **Mail-AI: Städa graf-spöknoder** (dygnsvis) — tar bort
  `:MailMessage`-noder vars Odoo-rad inte längre finns. Destruktivt, därför
  sällan och separat. Frågar grafen efter id:n (proportionellt mot antalet
  spöken, inte mot arkivet).

## Manuell uppdatering

**Min profil → fliken Preferences → Mail-minne → "Uppdatera mina
mail-minnen"** kör samma kärna som reparationen, scopad till din egen
postlåda (`env.user`). Rör aldrig någon annans mail.

## Konfiguration (ir.config_parameter)

- Batchstorlek och intervall sätts på respektive `ir.cron`.

