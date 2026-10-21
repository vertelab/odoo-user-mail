# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2024- Vertel Sverige AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
##############################################################################
"""Behörighet på den fristående formen E-postinställningar.

Formen öppnas av en server action som ALLTID sätter res_id = env.uid, men
det är bara ett UI-lager. Skyddet måste sitta i modellagret: en användare
i group_own_email_settings ska kunna skriva sina egna e-postfält, och
ingen annan ska komma åt dem.

Fallback om test_member_can_write_own_mail_fields faller: lägg fälten i
SELF_WRITEABLE_FIELDS (user_mail_common/models/res_users.py) — inte
sudo() i vyn. Se design.md, beslut 3.
"""

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOwnSettingsAccess(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group = cls.env.ref('user_mail_common.group_own_email_settings')
        Users = cls.env['res.users'].with_context(no_reset_password=True)

        cls.member = Users.create({
            'name': 'Mail Member',
            'login': 'mail.member@example.com',
            'email': 'mail.member@example.com',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.group.id,
            ])],
        })
        cls.outsider = Users.create({
            'name': 'Mail Outsider',
            'login': 'mail.outsider@example.com',
            'email': 'mail.outsider@example.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })

    # ── 4.1 ────────────────────────────────────────────────────────────

    def test_member_can_write_own_mail_fields(self):
        """Medlemmen ska kunna sätta semester, vidarebefordran och spam
        på sin egen post och läsa tillbaka värdet."""
        member = self.member.with_user(self.member)
        member.write({
            'vacation_active': True,
            'vacation_subject': 'Semester',
            'forward_active': True,
            'forward_address': 'cover@example.com',
            'spam_tag': '3',
        })
        member.invalidate_recordset()
        self.assertTrue(member.vacation_active)
        self.assertEqual(member.vacation_subject, 'Semester')
        self.assertTrue(member.forward_active)
        self.assertEqual(member.forward_address, 'cover@example.com')
        self.assertEqual(member.spam_tag, '3')

    def test_member_can_write_own_aliases(self):
        """Alias-listan på formen är en one2many — den ska gå att skriva."""
        member = self.member.with_user(self.member)
        member.write({
            'postfix_alias_ids': [(0, 0, {'name': 'alias', 'active': True})],
        })
        self.assertEqual(len(member.postfix_alias_ids), 1)

    # ── 4.2 ────────────────────────────────────────────────────────────

    def test_outsider_cannot_write_mail_fields(self):
        """Utan gruppen: ingen skrivrätt (AccessError), inte tyst no-op.

        Fallet är inte självklart: base.write() byter till sudo() så fort
        alla nycklar står i SELF_WRITEABLE_FIELDS, och prövar då aldrig
        ACL:er. Grinden är därför explicit (_check_mail_settings_rights i
        user_mail_common). Utan den skulle testet falla — det gjorde det
        också innan grinden fanns.
        """
        for values in (
            {'vacation_active': True},
            {'forward_active': True, 'forward_address': 'x@example.com'},
            {'spam_tag': '0'},
            {'postfix_alias_ids': [(0, 0, {'name': 'smygalias'})]},
        ):
            with self.assertRaises(AccessError, msg=str(values)):
                self.outsider.with_user(self.outsider).write(values)

    def test_outsider_cannot_write_mail_fields_via_mixed_payload(self):
        """Även när ett ofarligt fält blandas in ska grinden slå till."""
        with self.assertRaises(AccessError):
            self.outsider.with_user(self.outsider).write({
                'name': 'Mail Outsider',
                'vacation_active': True,
            })

    def test_outsider_keeps_ordinary_self_write(self):
        """Grinden får inte stänga av Odoos egna självservicfält —
        name/email/lang ska fortfarande gå att ändra utan gruppen."""
        outsider = self.outsider.with_user(self.outsider)
        outsider.write({'name': 'Mail Outsider Renamed'})
        self.assertEqual(outsider.name, 'Mail Outsider Renamed')

    def test_erp_manager_implies_the_group(self):
        """group_erp_manager ÄRVDE gruppen i user_mail_security.xml, så en
        administratör har den utan att den delas ut separat. Det är därför
        admin kan sätta mailfälten i användarformuläret.

        Testet låser det ärvda förhållandet: tas implied_ids bort blir
        administratörer utelåsta från egen e-post (men behåller skrivrätt
        via ACL på annans post)."""
        erp = self.env.ref('base.group_erp_manager')
        self.assertIn(self.group, erp.implied_ids)
        admin = self.env.ref('base.user_admin')
        self.assertIn(self.group, admin.groups_id)

    def test_admin_can_set_mail_fields(self):
        """Admin sätter fälten i användarformuläret — grinden ska inte
        stoppa den vägen."""
        admin = self.env.ref('base.user_admin')
        self.outsider.with_user(admin).write({'vacation_active': True})

    def test_outsider_does_not_get_the_group(self):
        """Gruppen är den enda grinden till menyn; den ska inte ärvas av
        base.group_user."""
        self.assertNotIn(self.group, self.outsider.groups_id)
        self.assertIn(self.group, self.member.groups_id)

    # ── 4.3 ────────────────────────────────────────────────────────────

    def test_member_cannot_write_other_user(self):
        """Medlemmen får skriva SIN post — inte någon annans. Det är detta
        som gör res_id = env.uid säkert."""
        with self.assertRaises(AccessError):
            self.outsider.with_user(self.member).write({
                'vacation_active': True,
            })

    def test_member_can_read_but_not_change_other_users(self):
        """base.group_user har läsrätt på res.users — att läsa någon annans
        post är alltså tillåtet. Det som måste nekas är SKRIVNINGEN, och
        det testas i test_member_cannot_write_other_user."""
        self.outsider.with_user(self.member).read(['postfix_mail'])
        with self.assertRaises(AccessError):
            self.outsider.with_user(self.member).write({'virus_active': False})

    def test_self_write_whitelist_does_not_leak_admin_fields(self):
        """SELF_WRITEABLE_FIELDS är en vitlista för skrivning på SIG SJÄLV.
        Fält som hör till admin eller servern får inte glida in där."""
        writeable = self.env['res.users'].SELF_WRITEABLE_FIELDS
        for forbidden in ('quota', 'postfix_mail', 'maildir',
                          'dovecot_password', 'groups_id', 'login'):
            self.assertNotIn(
                forbidden, writeable,
                "%s får inte vara självskrivbart" % forbidden)
        for expected in ('vacation_active', 'forward_active', 'spam_tag',
                         'postfix_alias_ids'):
            self.assertIn(expected, writeable)

    def test_self_write_whitelist_also_readable(self):
        """Allt som går att skriva på sig själv måste gå att läsa tillbaka,
        annars visas ett tomt fält efter spara i den fristående formen."""
        readable = self.env['res.users'].SELF_READABLE_FIELDS
        writeable = self.env['res.users'].SELF_WRITEABLE_FIELDS
        missing = {f for f in writeable
                   if not f.startswith('context_')} - set(readable)
        self.assertFalse(
            missing,
            "Skrivbara men inte läsbara fält ger tomma fält i formen: %s"
            % sorted(missing))

    # ── Vyn ────────────────────────────────────────────────────────────

    def test_own_settings_view_is_standalone(self):
        """Formen får inte ärva base.view_users_form_simple_modif — det var
        roten till att hela Min profil (alla flikar) dök upp."""
        view = self.env.ref('user_mail_client.view_user_mail_own_settings_form')
        self.assertFalse(
            view.inherit_id,
            "Den fristående formen ska inte ha inherit_id.")
        self.assertEqual(view.model, 'res.users')

    def test_own_settings_view_has_no_notebook(self):
        view = self.env.ref('user_mail_client.view_user_mail_own_settings_form')
        arch = view.arch_db or view.arch
        self.assertNotIn('<notebook', arch)
        self.assertNotIn('<page', arch)

    def test_action_opens_own_settings_view(self):
        action = self.env.ref('user_mail_client.action_user_mail_own_settings')
        self.assertEqual(action.state, 'code')
        self.assertEqual(action.groups_id, self.group)

    def test_menu_requires_group(self):
        menu = self.env.ref('user_mail_client.menu_user_mail_own_settings')
        self.assertIn(self.group, menu.groups_id)


class TestOwnSettingsViewArch(TransactionCase):
    """5.4/5.5 på ark-nivå: den fristående formen är flikfri och innehåller
    mailfälten; Min profil-vyn finns kvar orörd med sin flik."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.own = cls.env.ref(
            'user_mail_client.view_user_mail_own_settings_form')
        cls.profile = cls.env.ref(
            'user_mail_client.view_users_form_simple_modif_mail')

    def test_own_form_has_no_tabs(self):
        """5.4: menyns form ska inte ha någon notebook — det var hela
        problemet med den ärvda vyn."""
        arch = self.own.arch_db or self.own.arch
        self.assertNotIn('<notebook', arch)
        self.assertNotIn('<page', arch)

    def test_own_form_starts_with_name(self):
        """5.4: Name överst, mailfälten efter."""
        arch = self.own.arch_db or self.own.arch
        self.assertLess(arch.index('name="name"'),
                        arch.index('name="postfix_active"'))

    def test_own_form_carries_the_mail_fields(self):
        """5.4: fälten ska finnas i arch — annars renderas de inte."""
        arch = self.own.arch_db or self.own.arch
        for f in ('name', 'postfix_active', 'vacation_active',
                  'forward_active', 'spam_active', 'postfix_alias_ids',
                  'virus_active', 'mail_credentials_anchor'):
            self.assertIn('"%s"' % f if f != 'mail_credentials_anchor'
                          else 'mail_credentials_anchor', arch,
                          "saknas i arch: %s" % f)

    def test_own_form_has_no_foreign_tabs_content(self):
        """5.4: profildialogens fält ska inte läcka in."""
        arch = self.own.arch_db or self.own.arch
        for foreign in ('name="signature"', 'name="groups_id"',
                        'name="tz"', 'name="lang"'):
            self.assertNotIn(foreign, arch)

    def test_profile_tab_still_there(self):
        """5.5: Min profil behåller sin E-postinställningar-flik."""
        arch = self.profile.arch_db or self.profile.arch
        self.assertIn('mail_settings_page', arch)

    def test_gate_covers_every_self_writeable_mail_field(self):
        """Grinden får inte hamna på efterkälken: varje self-skrivbart
        mailfält måste också stå i MAIL_SETTINGS_FIELDS, annars blir det ett
        fält som vilken internal user som helst kan skriva på sig själv
        (base.write() gör sudo() utan gruppkontroll).

        "Mailfält" = de fält som user_mail_common äger på res.users, dvs.
        allt i SELF_WRITEABLE_FIELDS som inte kommer från Odoo själv.
        """
        Users = self.env['res.users']
        base_writeable = set(
            super(type(Users), Users).SELF_WRITEABLE_FIELDS)
        writeable = set(Users.SELF_WRITEABLE_FIELDS)
        mail_fields = writeable - base_writeable
        uncovered = mail_fields - set(Users.MAIL_SETTINGS_FIELDS)
        self.assertFalse(
            uncovered,
            "self-skrivbara mailfält utan gruppgrind: %s" % sorted(uncovered))
