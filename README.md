# odoo-user-mail — gren 19.0

> **Denna gren är avsiktligt tom.** Modulerna är INTE portade till Odoo 19.
> Grenen finns så att dev-miljöer (`hansolo19`) kan klona den utan att falla,
> men den påstår ingenting om att koden är portad.

## Baseline

| | |
|---|---|
| Källa | `20.0` |
| Moduler | **11** |
| Grenar i repot | `12.0`, `12.0-af`, `12.0-test`, `13.0`, `13.0-Mail`, `14.0`, `15.0`, `16.0`, `17.0`, `18.0`, `20.0`, `8.0`, `Added-description-to-the-module`, `inc-2026-10-19-imap-memory`, `master`, `master10`, `port-to-14`, `user-mail-server-v12` |

## Moduler

- `user_mail_ai`
- `user_mail_client`
- `user_mail_common`
- `user_mail_imap`
- `user_mail_onboarding`
- `user_mail_server`
- `user_password_strength`
- `user_password_tmp`
- `user_scim`
- `user_scim_admin`
- `user_scim_matrix`

## Blockerare

**1 externa beroenden saknas** i Odoo 19-kärnan och OCA 19.0:

| Beroende | Behövs av |
|---|---|
| `user_matrix` | `user_scim_matrix` |

### Prioritering

Ett beroende som blockerar många moduler ger mest nytta att lösa först:

- `user_matrix` — frisläpper **1** modul(er)

## Nästa steg

Portering sker på `*-pfile`-maskin med versionsagnostisk kod
(`.p.py` / `.p.xml`). Se `/skill:odoo-pfiles`.
