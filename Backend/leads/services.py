"""Lead status transitions and CRM conversion.

Conversion is atomic, transactional, idempotent, and duplicate-aware: the lead
row is locked, the terminal/converted guards run inside the transaction, and a
second concurrent attempt cannot create a second client/deal.
"""
from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from audit.models import AuditCategory
from audit.services import record_event
from clients.models import Client
from sales.models import Deal, Pipeline

from .models import Lead, LeadStatus


class LeadError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def find_matching_clients(lead: Lead):
    """Existing CRM companies that may already represent this lead."""
    filters = Q(name__iexact=lead.name)
    if lead.normalized_phone:
        filters |= Q(phone=lead.normalized_phone) | Q(phone=lead.original_phone)
    return Client.objects.filter(filters).distinct()


def mark_viewed(lead: Lead, user, request=None):
    if lead.first_viewed_at is None:
        lead.first_viewed_at = timezone.now()
        lead.save(update_fields=["first_viewed_at", "updated_at"])
        record_event(
            action="lead.viewed",
            category=AuditCategory.LEAD,
            user=user,
            request=request,
            entity_type="Lead",
            entity_id=lead.pk,
            summary=f"Lead '{lead.name}' opened for the first time.",
        )
    return lead


def reopen_lead(lead: Lead, admin, reason: str, request=None):
    """Admin-only: reopen a terminal lead with a required reason (audited)."""
    if not lead.is_terminal:
        raise LeadError("not_terminal", "Only terminal leads (not interested / converted) can be reopened.")
    if not (reason or "").strip():
        raise LeadError("reason_required", "A reason is required to reopen a terminal lead.")
    old_status = lead.status
    lead.status = LeadStatus.NEW
    lead.reopened_reason = reason.strip()
    lead.save(update_fields=["status", "reopened_reason", "updated_at"])
    record_event(
        action="lead.reopened",
        category=AuditCategory.LEAD,
        user=admin,
        request=request,
        entity_type="Lead",
        entity_id=lead.pk,
        summary=f"Lead '{lead.name}' reopened from {old_status}.",
        old_values={"status": old_status},
        new_values={"status": lead.status, "reason": reason.strip()},
    )
    return lead


def _default_pipeline_and_stage():
    pipeline = Pipeline.objects.filter(is_default=True).first() or Pipeline.objects.first()
    if pipeline is None:
        return None, None
    stage = pipeline.stages.order_by("order", "name").first()
    return pipeline, stage


@transaction.atomic
def convert_lead(
    lead_id: int,
    user,
    *,
    existing_client_id=None,
    create_deal=False,
    deal_title="",
    deal_value=None,
    deal_currency="JOD",
    reason="",
    work_session=None,
    request=None,
):
    """Convert a lead into (or link it to) a CRM client, optionally with a deal.

    Returns ``(lead, client, deal_or_None)``.
    """
    lead = Lead.objects.select_for_update().filter(pk=lead_id).first()
    if lead is None:
        raise LeadError("not_found", "Lead not found.")

    # Guards (inside the lock so a race cannot bypass them).
    if lead.status == LeadStatus.CONVERTED or lead.converted_client_id:
        raise LeadError("already_converted", "This lead has already been converted.")
    if lead.status == LeadStatus.NOT_INTERESTED:
        raise LeadError("terminal", "This lead is marked not interested. An admin must reopen it before conversion.")
    if lead.status == LeadStatus.NO_ANSWER and not (reason or "").strip():
        # No-answer conversion must be a deliberate act with a reason.
        raise LeadError("reason_required", "Converting a no-answer lead requires a reason.")

    # Link to an existing client or create a new one.
    if existing_client_id:
        client = Client.objects.filter(pk=existing_client_id).first()
        if client is None:
            raise LeadError("client_not_found", "The selected existing client does not exist.")
        created_client = False
    else:
        client = Client.objects.create(
            name=lead.name,
            phone=lead.normalized_phone or lead.original_phone,
            notes=f"Converted from lead #{lead.pk}." + (f" {reason}" if reason else ""),
            created_by=user if getattr(user, "is_authenticated", False) else None,
        )
        created_client = True

    deal = None
    if create_deal:
        pipeline, stage = _default_pipeline_and_stage()
        if pipeline is None or stage is None:
            raise LeadError("no_pipeline", "No sales pipeline is configured to create a deal.")
        deal = Deal.objects.create(
            title=deal_title or f"{lead.name} — new opportunity",
            company=client,
            contact_person=lead.name,
            value=deal_value,
            currency=deal_currency or "JOD",
            pipeline=pipeline,
            stage=stage,
            owner=user,
        )

    lead.status = LeadStatus.CONVERTED
    lead.converted_client = client
    lead.converted_deal = deal
    lead.converted_by = user if getattr(user, "is_authenticated", False) else None
    lead.converted_at = timezone.now()
    if reason:
        lead.reopened_reason = lead.reopened_reason  # unchanged; reason recorded in audit
    lead.save(update_fields=["status", "converted_client", "converted_deal", "converted_by", "converted_at", "updated_at"])

    record_event(
        action="lead.converted",
        category=AuditCategory.LEAD,
        user=user,
        request=request,
        work_session=work_session,
        entity_type="Lead",
        entity_id=lead.pk,
        summary=(
            f"Lead '{lead.name}' converted to client #{client.pk}"
            + (f" and deal #{deal.pk}" if deal else "")
            + ("." if not reason else f" (reason: {reason})")
        ),
        metadata={
            "client_id": client.pk,
            "client_created": created_client,
            "deal_id": deal.pk if deal else None,
        },
    )
    return lead, client, deal
