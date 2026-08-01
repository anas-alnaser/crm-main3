"""Tests for the reset_crm_data management command."""
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import User
from clients.models import Client
from crm.test_data_reset import ResetFixtureMixin


class ResetCommandTests(ResetFixtureMixin):
    def setUp(self):
        super().setUp()
        self.superadmin = self.make_superadmin(username="owner", password="ownerpass123")
        self.seed_business_data(owner=self.superadmin)

    def _run(self, **kwargs):
        out = StringIO()
        call_command("reset_crm_data", stdout=out, stderr=StringIO(), **kwargs)
        return out.getvalue()

    def test_requires_exactly_one_selector(self):
        with self.assertRaises(CommandError):
            self._run(dry_run=True)  # neither
        with self.assertRaises(CommandError):
            self._run(keep_user_id=self.superadmin.id, keep_user_email="owner@example.com", dry_run=True)

    def test_rejects_non_superadmin(self):
        with self.assertRaises(CommandError):
            self._run(keep_user_id=self.rep.id, dry_run=True)

    def test_dry_run_makes_no_changes(self):
        out = self._run(keep_user_id=self.superadmin.id, dry_run=True)
        self.assertIn("DRY RUN", out)
        self.assertTrue(Client.objects.filter(name="Acme").exists())
        self.assertTrue(User.objects.filter(username="rep1").exists())

    def test_real_reset_requires_confirm_phrase(self):
        with self.assertRaises(CommandError):
            self._run(keep_user_id=self.superadmin.id, allow_non_postgres=True)
        self.assertTrue(Client.objects.exists())

    def test_refuses_non_postgres_without_flag(self):
        with self.assertRaises(CommandError):
            self._run(keep_user_id=self.superadmin.id, confirm="DELETE ALL CRM DATA")
        self.assertTrue(Client.objects.exists())

    def test_real_reset_executes_with_flag(self):
        out = self._run(
            keep_user_id=self.superadmin.id,
            confirm="DELETE ALL CRM DATA",
            allow_non_postgres=True,
        )
        self.assertIn("reset completed", out.lower())
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(Client.objects.exists())
        self.assertTrue(User.objects.filter(pk=self.superadmin.id).exists())
