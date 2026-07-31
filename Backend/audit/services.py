"""Helpers for recording audit events safely from anywhere in the backend.

Call :func:`record_event` for server-authoritative events. Request metadata
(IP, user-agent, request id) is extracted when a DRF/Django request is passed;
credentials are never read from it.
"""
from __future__ import annotations

import logging

from .models import AuditCategory, AuditEvent, AuditSource
from .redaction import redact

logger = logging.getLogger("audit")


def client_ip(request):
    """Best-effort client IP, honouring a single proxy hop if present."""
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def user_agent(request):
    if request is None:
        return ""
    return (request.META.get("HTTP_USER_AGENT") or "")[:400]


def request_id(request):
    if request is None:
        return ""
    return (request.META.get("HTTP_X_REQUEST_ID") or "")[:64]


def record_event(
    *,
    action,
    category,
    user=None,
    request=None,
    work_session=None,
    entity_type="",
    entity_id="",
    summary="",
    metadata=None,
    old_values=None,
    new_values=None,
    source=AuditSource.SERVER,
    ip_address=None,
    commit=True,
):
    """Create (and optionally save) an :class:`AuditEvent`.

    All free-form payloads are passed through :func:`redact` so sensitive keys
    never reach the database. Failures to log are swallowed and logged to the
    application logger — auditing must never break the underlying business
    action.
    """
    if category not in AuditCategory.values:
        category = AuditCategory.CRM

    event = AuditEvent(
        user=user if getattr(user, "is_authenticated", False) else None,
        work_session=work_session,
        action=str(action)[:64],
        category=category,
        source=source,
        entity_type=str(entity_type)[:64],
        entity_id="" if entity_id is None else str(entity_id)[:64],
        summary=str(summary),
        request_id=request_id(request),
        metadata=redact(metadata or {}),
        old_values=redact(old_values or {}),
        new_values=redact(new_values or {}),
        ip_address=ip_address if ip_address is not None else client_ip(request),
        user_agent=user_agent(request),
    )
    if commit:
        try:
            event.save()
        except Exception:  # pragma: no cover - defensive; auditing must not break flow
            logger.exception("Failed to persist audit event action=%s", action)
            return None
    return event
