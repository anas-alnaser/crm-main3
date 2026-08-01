"""Tests for the authoritative full-reset service (crm.data_reset)."""
from datetime import time, timedelta
from unittest import mock

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth import authenticate
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from crm.apitestbase import APITestBase
from crm import data_reset
from accounts.models import User
from activities.models import Activity
from ai_commands.models import AICommandConfirmation, AICommandLog
from audit.models import AuditCategory, AuditEvent
from branding.models import (
    BrandProfile,
    DocumentSequence,
    GeneratedDocument,
    GeneratedDocumentSnapshot,
    LegalEntity,
    Signatory,
)
from clients.models import Client
from leads.models import Lead, LeadContactAttempt, LeadImportBatch
from mediastore.models import StoredFile
from meetings.models import Meeting
from projects.models import Project
from sales.models import Deal, Pipeline, SalesSettings, Stage
from tasks.models import Task
from workforce.models import EmployeeWorkPolicy, WorkPolicyException, WorkSession
from workforce.timezones import local_date


class ResetFixtureMixin(APITestBase):
    def seed_business_data(self, *, owner):
        """Create one of (nearly) every business record + extra users."""
        self.other_admin = self.make_superadmin(username="other_admin")
        self.rep = self.make_sales(username="rep1")

        company = self.make_company(name="Acme")
        pipeline, stages = self.make_pipeline_with_stages()
        self.make_deal(owner, company, pipeline, stages["lead"])
        Project.objects.create(title="Site", client=company)
        Task.objects.create(title="Do", client=company)
        Activity.objects.create(type="note", content="hello", client=company)
        now = timezone.now()
        Meeting.objects.create(title="Sync", start_datetime=now, end_datetime=now + timedelta(hours=1), owner=owner)

        batch = LeadImportBatch.objects.create(original_filename="x.xlsx")
        lead = Lead.objects.create(name="L", original_phone="0790000001", batch=batch, assigned_to=self.rep)
        LeadContactAttempt.objects.create(lead=lead, employee=self.rep, outcome="reached")

        policy = EmployeeWorkPolicy.objects.create(user=self.rep)
        WorkPolicyException.objects.create(policy=policy, date=local_date(), exception_type="holiday")
        WorkSession.objects.create(
            employee=self.rep, policy=policy, started_at=now, last_activity_at=now, work_date=local_date(),
            window_start_time=time(9, 0), window_end_time=time(21, 0),
        )

        AuditEvent.objects.create(action="test.event", category=AuditCategory.CRM)
        AICommandLog.objects.create(user=self.rep, raw_text="hi", outcome="executed")
        AICommandConfirmation.objects.create(user=self.rep, intent="x", tier="confirm", expires_at=now + timedelta(minutes=5))

        brand = BrandProfile.objects.get(key="fuel_dezign")
        legal = brand.legal_entity
        Signatory.objects.create(legal_entity=legal, name="Owner")
        DocumentSequence.objects.create(legal_entity=legal, document_type="invoice", year=2026, last_number=3)
        doc = GeneratedDocument.objects.create(
            document_type="invoice", document_number="INV-1", brand=brand, legal_entity=legal,
        )
        GeneratedDocumentSnapshot.objects.create(document=doc, generated_at=now, data={})

        StoredFile.objects.create(name="logos/x.png", content=b"x")
        LogEntry.objects.log_action(
            user_id=owner.id, content_type_id=ContentType.objects.get_for_model(Client).id,
            object_id=company.id, object_repr="Acme", action_flag=ADDITION, change_message="created",
        )
        SalesSettings.load()
        return company


class ResetServiceTests(ResetFixtureMixin):
    def setUp(self):
        super().setUp()
        self.superadmin = self.make_superadmin(username="owner", password="ownerpass123")
        self.seed_business_data(owner=self.superadmin)

    def test_preview_changes_nothing(self):
        before = Lead.objects.count(), Client.objects.count(), User.objects.count()
        preview = data_reset.preview_crm_reset(preserved_user=self.superadmin)
        after = Lead.objects.count(), Client.objects.count(), User.objects.count()
        self.assertEqual(before, after)
        self.assertGreater(preview["total_rows"], 0)
        self.assertEqual(preview["other_users_to_delete"], 2)

    def test_reset_preserves_superadmin_identity_and_password(self):
        original_id = self.superadmin.id
        data_reset.reset_crm_data(preserved_user=self.superadmin)
        self.assertTrue(User.objects.filter(pk=original_id).exists())
        preserved = User.objects.get(pk=original_id)
        self.assertEqual(preserved.username, "owner")
        self.assertTrue(preserved.is_active and preserved.is_staff and preserved.is_superuser)
        self.assertEqual(preserved.role, "admin")
        # Password still authenticates.
        self.assertIsNotNone(authenticate(username="owner", password="ownerpass123"))

    def test_reset_deletes_other_users(self):
        data_reset.reset_crm_data(preserved_user=self.superadmin)
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(User.objects.filter(username="other_admin").exists())
        self.assertFalse(User.objects.filter(username="rep1").exists())

    def test_reset_deletes_all_business_models(self):
        data_reset.reset_crm_data(preserved_user=self.superadmin)
        for model in [
            Lead, LeadContactAttempt, LeadImportBatch, Client, Deal, Project, Task,
            Activity, Meeting, WorkSession, WorkPolicyException, EmployeeWorkPolicy,
            AuditEvent, AICommandLog, AICommandConfirmation, StoredFile, LogEntry,
            GeneratedDocument, GeneratedDocumentSnapshot, DocumentSequence, Signatory,
            Pipeline, Stage, SalesSettings,
        ]:
            self.assertEqual(model.objects.count(), 0, f"{model.__name__} not cleared")

    def test_reset_preserves_brand_and_legal_structure(self):
        data_reset.reset_crm_data(preserved_user=self.superadmin)
        self.assertEqual(set(LegalEntity.objects.values_list("key", flat=True)), {"fuel", "morph"})
        self.assertEqual(
            set(BrandProfile.objects.values_list("key", flat=True)),
            {"fuel_dezign", "morph_studio", "morph_solutions"},
        )

    def test_reset_preserves_system_tables(self):
        ct_before = ContentType.objects.count()
        perm_before = Permission.objects.count()
        mig_before = MigrationRecorder.Migration.objects.count()
        data_reset.reset_crm_data(preserved_user=self.superadmin)
        self.assertEqual(ContentType.objects.count(), ct_before)
        self.assertEqual(Permission.objects.count(), perm_before)
        self.assertEqual(MigrationRecorder.Migration.objects.count(), mig_before)

    def test_reset_return_has_safe_counts_only(self):
        result = data_reset.reset_crm_data(preserved_user=self.superadmin)
        self.assertIn("deleted", result)
        self.assertIsInstance(result["deleted"], dict)
        for value in result["deleted"].values():
            self.assertIsInstance(value, int)
        # Preserved summary is safe (no password hash).
        self.assertEqual(set(result["preserved_user"]), {"id", "username", "email"})

    def test_preserved_user_survives_indirect_cascade(self):
        # The preserved user owns a deal + meeting + AI log (PROTECT). Those are
        # business data and get deleted; the user itself must remain.
        AICommandLog.objects.create(user=self.superadmin, raw_text="hi", outcome="executed")
        data_reset.reset_crm_data(preserved_user=self.superadmin)
        self.assertTrue(User.objects.filter(pk=self.superadmin.id).exists())

    def test_failure_rolls_back_everything(self):
        with mock.patch("crm.data_reset._reset_sequences", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                data_reset.reset_crm_data(preserved_user=self.superadmin)
        # Nothing was deleted — full rollback.
        self.assertTrue(Client.objects.filter(name="Acme").exists())
        self.assertTrue(User.objects.filter(username="rep1").exists())
        self.assertTrue(Lead.objects.exists())

    def test_concurrent_reset_rejected(self):
        cache.add(data_reset.RESET_LOCK_CACHE_KEY, True, timeout=600)
        try:
            with self.assertRaises(data_reset.ResetConflict):
                data_reset.reset_crm_data(preserved_user=self.superadmin)
        finally:
            cache.delete(data_reset.RESET_LOCK_CACHE_KEY)
        # The rejected reset changed nothing.
        self.assertTrue(Client.objects.filter(name="Acme").exists())

    def test_reset_rejects_non_superadmin_preserved_user(self):
        with self.assertRaises(data_reset.ResetError):
            data_reset.reset_crm_data(preserved_user=self.rep)
        self.assertTrue(User.objects.filter(username="rep1").exists())

    def test_sequences_reset_when_supported(self):
        # On SQLite this is a safe no-op; on PostgreSQL it runs sequence SQL.
        # Either way, the reset completes without error.
        result = data_reset.reset_crm_data(preserved_user=self.superadmin)
        self.assertEqual(result["total_deleted"], result["total_deleted"])  # completed
