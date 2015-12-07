```
INSTALL INSTRUCTIONS

Installing user_mail_client will make the clients update server when changes occur to users or companies,
intall the user_mail_server on the main server database to make it recieve updates from clients.

Note that user_mail_common contains fields and functions that both user_mail_client and user_mail_server share and both the modules depend on user_mail_common.

The intended purpose user_mail modules is only for dovecot/postfix. Not for regular Odoo usage.


-------/etc/odoo/openerp-server.conf-------

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
query = SELECT login FROM res_users WHERE login='%s' and active = '1'  and forward_active = '0'


-------/etc/postfix/virtual_alias_maps.cf-------

user = <postgres user>
password = <postgres user password>
hosts = <main server>
dbname = <main server dbname (passwd_dbname)> 
table = postfix_alias p, res_users r 
select_field = login 
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
select_field = forward_address||', '||login 
where_field = login
additional_conditions = and forward_active = '1' and forward_cp = '1' 


-------/etc/postfix/virtual_forward_maps.cf-------

user = <postgres user>
password = <postgres user password>
hosts = <main server>
dbname = <main server dbname (passwd_dbname)> 
table = res_users 
select_field = forward_address 
where_field = login
additional_conditions = and forward_active = '1' and forward_cp = '0' 

-------/etc/postfix/virtual_mailbox_limit_maps.cf-------

user = <postgres user>
password = <postgres user password>
hosts = <main server>
dbname = <main server dbname (passwd_dbname)> 
table = res_users  
select_field = quota
where_field = login 
additional_conditions = and postfix_active = '1'

-------/etc/postfix/virtual_mailbox_maps.cf-------

user = <postgres user>
password = <postgres user password>
hosts = <main server>
dbname = <main server dbname (passwd_dbname)> 
table = res_users  
select_field = maildir
where_field = login 
additional_conditions = and postfix_active = '1' 
```
