# -*- coding: utf-8 -*-
"""Wizarden user.mail.imap.password.wizard saknade ACL i modulens första
version. Knappen syntes, men att klicka på den gav "Du har inte åtkomst
till Set IMAP Password" — på båda ytorna (Min profil och
E-postinställningar). Testerna här låser att wizarden är körbar för en
medlem i group_own_email_settings och stängd för alla andra.
"""
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

WIZARD = 'user.mail.imap.password.wizard'


@tagged('post_install', '-at_install')
class TestPasswordWizardAcl(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.group = cls.env.ref('user_mail_common.group_own_email_settings')
        cls.member = Users.create({
            'name': 'Wizard Member',
            'login': 'wizard.member@example.com',
            'email': 'wizard.member@example.com',
            # #if VERSION >= "19.0"
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.group.id])],
            # #else
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id,
                                  cls.group.id])],
            # #endif
        })
        cls.outsider = Users.create({
            'name': 'Wizard Outsider',
            'login': 'wizard.outsider@example.com',
            'email': 'wizard.outsider@example.com',
            # #if VERSION >= "19.0"
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
            # #else
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
            # #endif
        })
        # #if VERSION >= "20.0"
        for _u, _groups in (
                (cls.member, [cls.env.ref('base.group_user').id,
                              cls.group.id]),
                (cls.outsider, [cls.env.ref('base.group_user').id])):
            cls.env.cr.execute(
                'DELETE FROM res_groups_users_rel WHERE uid = %s', (_u.id,))
            for _g in _groups:
                cls.env.cr.execute(
                    'INSERT INTO res_groups_users_rel (uid, gid) '
                    'VALUES (%s, %s) ON CONFLICT DO NOTHING', (_u.id, _g))
        cls.env.invalidate_all()
        # #endif

    def test_acl_row_exists_for_the_group(self):
        """Utan ACL-rad nekar Odoo varje användning av wizarden, även för
        dem som har gruppen — det var buggen."""
        # #if VERSION >= "20.0"
        # Odoo 20: ir.model.access heter ir.access.
        acl = self.env['ir.access'].search([
            ('model_id.model', '=', WIZARD),
        ])
        # #else
        acl = self.env['ir.model.access'].search([
            ('model_id.model', '=', WIZARD),
        ])
        # #endif
        self.assertTrue(acl, "wizarden saknar ir.model.access-rad")
        self.assertIn(self.group, acl.group_id,
                      "ACL:n måste gälla group_own_email_settings")

    def test_member_can_open_and_run_the_wizard(self):
        """Medlemmen ska kunna skapa wizarden — annars går knappen inte att
        använda. (Själva lösenordsverifieringen kräver en riktig
        dovecot-hash och testas i IMAP-sviten.)"""
        wizard = self.env[WIZARD].with_user(self.member).create({
            'password': 'x',
        })
        self.assertTrue(wizard)

    def test_outsider_cannot_open_the_wizard(self):
        """Lösenordet sätter mailkontot — gruppen ska krävas, inte bara
        base.group_user."""
        with self.assertRaises(AccessError):
            self.env[WIZARD].with_user(self.outsider).create({
                'password': 'x',
            })
