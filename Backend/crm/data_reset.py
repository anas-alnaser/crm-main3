"""Full CRM reset — the single authoritative implementation.

Both the API endpoint (``crm.reset_views``) and the management command
(``accounts.management.commands.reset_crm_data``) call this module; the reset
logic is never duplicated.

What a reset does:
    * Permanently deletes all CRM business data and every application user
      *except* the preserved superadmin.
    * Preserves the preserved user (same id, username, email, password hash, and
      active/staff/superuser/admin flags), the database schema, migrations,
      content types, permissions, and the required Fuel/Morph brand + legal
      structure (reseeded idempotently from the authoritative migration seed).

Safety properties:
    * One ``transaction.atomic()`` — any failure rolls the whole reset back.
    * The preserved user is locked with ``select_for_update`` and revalidated
      before and after the deletions; it is excluded from every delete and can
      never be removed by a cascade (all PROTECT references to users are cleared
      first by deleting the business data).
    * A PostgreSQL advisory lock (cache fallback off-Postgres) prevents two
      resets from running at once.
    * FK-aware deletion order — children before parents — so nothing is deleted
      out from under a PROTECT/foreign-key constraint. No constraint is ever
      disabled and ``TRUNCATE CASCADE`` is never used.
    * Sequences for the fully-cleared business tables are reset on PostgreSQL.
    * Returned payloads contain safe per-model counts only — never field values.
"""
from __future__ import annotations

import contextlib
import importlib

from django.contrib.admin.models import LogEntry
from django.core.management.color import no_style
from django.db import connection, transaction

from accounts.models import User
from activities.models import Activity
from ai_commands.models import AICommandConfirmation, AICommandLog
from audit.models import AuditEvent
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

# Fixed 63-bit key for the PostgreSQL session advisory lock.
RESET_LOCK_KEY = 728510394027
RESET_LOCK_CACHE_KEY = "crm:data_reset:running"

# The required brand/legal structure that must survive a reset (reseeded from the
# authoritative branding migration below).
REQUIRED_LEGAL_KEYS = ["fuel", "morph"]
REQUIRED_BRAND_KEYS = ["fuel_dezign", "morph_studio", "morph_solutions"]


class ResetError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class ResetConflict(ResetError):
    """Raised when a reset is already running (maps to HTTP 409)."""


def _validate_preserved(user) -> None:
    """The preserved user must be a full superadmin (see accounts.permissions)."""
    if user is None:
        raise ResetError("no_user", "A preserved user is required.")
    ok = (
        user.is_active
        and user.is_staff
        and user.is_superuser
        and getattr(user, "role", None) == "admin"
    )
    if not ok:
        raise ResetError(
            "not_superadmin",
            "The preserved user must be an active superadmin (staff + superuser + admin role).",
        )


def _deletion_plan(preserved_user):
    """Ordered (label, queryset) pairs, children before parents.

    Every business row is removed; only the preserved user is excluded. By the
    time users are deleted, all PROTECT references to them (deals, meetings,
    AI-command logs) are already gone, so the delete is constraint-safe and the
    preserved user can be excluded without any cascade reaching it.
    """
    return [
        ("audit_events", AuditEvent.objects.all()),
        ("ai_command_confirmations", AICommandConfirmation.objects.all()),
        ("ai_command_logs", AICommandLog.objects.all()),
        ("document_snapshots", GeneratedDocumentSnapshot.objects.all()),
        ("generated_documents", GeneratedDocument.objects.all()),
        ("document_sequences", DocumentSequence.objects.all()),
        ("signatories", Signatory.objects.all()),
        ("lead_contact_attempts", LeadContactAttempt.objects.all()),
        ("leads", Lead.objects.all()),
        ("lead_import_batches", LeadImportBatch.objects.all()),
        ("tasks", Task.objects.all()),
        ("activities", Activity.objects.all()),
        ("meetings", Meeting.objects.all()),
        ("deals", Deal.objects.all()),
        ("projects", Project.objects.all()),
        ("companies", Client.objects.all()),
        ("stages", Stage.objects.all()),
        ("pipelines", Pipeline.objects.all()),
        ("sales_settings", SalesSettings.objects.all()),
        ("work_sessions", WorkSession.objects.all()),
        ("work_policy_exceptions", WorkPolicyException.objects.all()),
        ("work_policies", EmployeeWorkPolicy.objects.all()),
        ("stored_files", StoredFile.objects.all()),
        ("admin_log_entries", LogEntry.objects.all()),
        # Users LAST — after every PROTECT reference to them is gone.
        ("other_users", User.objects.exclude(pk=preserved_user.pk)),
    ]


# Models whose PostgreSQL identity sequence is safe to reset to 1 (fully cleared).
# accounts.User is intentionally excluded — the preserved user keeps its id.
_SEQUENCE_RESET_MODELS = [
    AuditEvent, AICommandConfirmation, AICommandLog, GeneratedDocumentSnapshot,
    GeneratedDocument, DocumentSequence, Signatory, LeadContactAttempt, Lead,
    LeadImportBatch, Task, Activity, Meeting, Deal, Project, Client, Stage,
    Pipeline, SalesSettings, WorkSession, WorkPolicyException, EmployeeWorkPolicy,
    StoredFile, LogEntry,
]


def _preserved_summary(user) -> dict:
    return {"id": user.id, "username": user.username, "email": user.email}


def _preserved_config() -> dict:
    """The brand/legal structure that will be preserved / reseeded (safe labels)."""
    return {
        "legal_entities": list(
            LegalEntity.objects.filter(key__in=REQUIRED_LEGAL_KEYS).values_list("legal_name", flat=True)
        ),
        "brands": list(
            BrandProfile.objects.filter(key__in=REQUIRED_BRAND_KEYS).values_list("display_name", flat=True)
        ),
    }


@contextlib.contextmanager
def _reset_lock():
    """Serialise resets. PostgreSQL advisory lock in production; a cache-based
    fallback for SQLite (dev/tests) so concurrency is still guarded and testable."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [RESET_LOCK_KEY])
            acquired = cursor.fetchone()[0]
        if not acquired:
            raise ResetConflict("reset_in_progress", "A CRM data reset is already running.")
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [RESET_LOCK_KEY])
    else:
        from django.core.cache import cache

        if not cache.add(RESET_LOCK_CACHE_KEY, True, timeout=600):
            raise ResetConflict("reset_in_progress", "A CRM data reset is already running.")
        try:
            yield
        finally:
            cache.delete(RESET_LOCK_CACHE_KEY)


def _seed_brand_structure() -> None:
    """Reseed the required Fuel/Morph brand + legal structure using the
    authoritative branding migration seed (idempotent get_or_create; no fabricated
    legal identifiers)."""
    from django.apps import apps as django_apps

    seed_module = importlib.import_module("branding.migrations.0002_seed_brands")
    seed_module.seed(django_apps, None)


def _reset_sequences() -> None:
    if connection.vendor != "postgresql":
        return
    statements = connection.ops.sequence_reset_sql(no_style(), _SEQUENCE_RESET_MODELS)
    if not statements:
        return
    with connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql)


# Tables written by ordinary activity (including the preview/execute requests
# themselves) — excluded from the token fingerprint so an incidental audit or
# admin-log write between preview and execute does not needlessly invalidate a
# fresh preview. Business tables (companies, leads, deals, users…) still bind, so
# a real data change — or a completed reset — correctly invalidates the token.
_SNAPSHOT_VOLATILE = {"audit_events", "admin_log_entries"}


def snapshot_hash(preserved_user) -> str:
    """A short, stable fingerprint of the current reset scope.

    Binds a preview token to the data state it previewed: after a reset the
    counts drop, so a token issued for the old state no longer matches — giving
    practical single-use even across worker processes. Never includes any field
    values, only the preserved user id and the per-model counts of stable
    business tables."""
    import hashlib

    counts = {
        label: qs.count()
        for label, qs in _deletion_plan(preserved_user)
        if label not in _SNAPSHOT_VOLATILE
    }
    payload = f"{preserved_user.pk}|" + "|".join(f"{k}={counts[k]}" for k in sorted(counts))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def preview_crm_reset(*, preserved_user) -> dict:
    """Read-only. Return per-model counts and preserved/reseeded config. No writes."""
    _validate_preserved(preserved_user)
    counts = {label: qs.count() for label, qs in _deletion_plan(preserved_user)}
    other_users = counts.get("other_users", 0)
    return {
        "preserved_user": _preserved_summary(preserved_user),
        "counts": counts,
        "other_users_to_delete": other_users,
        "total_rows": sum(counts.values()),
        "preserved_config": _preserved_config(),
        "snapshot": snapshot_hash(preserved_user),
    }


def reset_crm_data(*, preserved_user) -> dict:
    """Execute the full reset. Transactional, locked, and rolled back on any error.

    Returns safe per-model deletion counts plus the preserved user summary."""
    _validate_preserved(preserved_user)

    with _reset_lock():
        with transaction.atomic():
            # Lock the preserved user for the whole operation and revalidate it
            # under the lock so its flags cannot change mid-reset.
            locked_user = User.objects.select_for_update().get(pk=preserved_user.pk)
            _validate_preserved(locked_user)

            deleted: dict[str, int] = {}
            for label, queryset in _deletion_plan(locked_user):
                count = queryset.count()
                queryset.delete()
                deleted[label] = count

            # Reseed the required brand/legal structure (safety net; they are
            # preserved, not deleted) and reset business-table sequences.
            _seed_brand_structure()
            _reset_sequences()

            # Final revalidation: the preserved user must still be a superadmin
            # with an unchanged id after everything.
            locked_user.refresh_from_db()
            _validate_preserved(locked_user)
            assert locked_user.pk == preserved_user.pk

    return {
        "preserved_user": _preserved_summary(preserved_user),
        "deleted": deleted,
        "total_deleted": sum(deleted.values()),
        "reseeded_config": _preserved_config(),
    }
