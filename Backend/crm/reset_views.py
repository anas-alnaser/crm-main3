"""Full CRM reset API — superadmin only, preview-gated, rate-limited.

    GET  /api/admin/data-reset/preview/   -> counts + a short-lived preview token
    POST /api/admin/data-reset/execute/   -> performs the reset (test/prod DB)

Execute requires re-authentication (current password), the exact confirmation
phrase ``DELETE ALL CRM DATA``, ``preserved_user_id == request.user.id``, and a
fresh, valid preview token bound to the previewed data snapshot. The token is
signed, expires after ~10 minutes, and is single-use. Neither the password nor
the token is ever logged.
"""
from __future__ import annotations

import secrets
from datetime import timedelta

from django.core import signing
from django.core.cache import cache
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsSuperAdmin
from audit.models import AuditCategory
from audit.services import record_event
from crm import danger
from crm.data_reset import (
    ResetConflict,
    ResetError,
    preview_crm_reset,
    reset_crm_data,
    snapshot_hash,
)
from crm.throttling import DangerZoneThrottle

PREVIEW_SALT = "crm.data_reset.preview.v1"
PREVIEW_TTL_SECONDS = 600  # 10 minutes
CONFIRMATION_PHRASE = "DELETE ALL CRM DATA"


class PreviewTokenError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _nonce_key(jti: str) -> str:
    return f"crm:reset:preview:{jti}"


def issue_preview_token(user, snapshot: str) -> str:
    """Sign a single-use token binding the preserved user, the previewed snapshot,
    and an expiry. A per-token nonce is recorded in the cache for single-use;
    the snapshot binding additionally invalidates the token once the data changes
    (e.g. after a successful reset)."""
    jti = secrets.token_urlsafe(12)
    cache.set(_nonce_key(jti), True, PREVIEW_TTL_SECONDS)
    return signing.dumps({"puid": user.id, "snap": snapshot, "jti": jti}, salt=PREVIEW_SALT)


def consume_preview_token(token: str, user) -> dict:
    if not token:
        raise PreviewTokenError("preview_required", "A fresh preview is required before executing a reset.")
    try:
        data = signing.loads(token, salt=PREVIEW_SALT, max_age=PREVIEW_TTL_SECONDS)
    except signing.SignatureExpired:
        raise PreviewTokenError("preview_expired", "The preview has expired. Preview again before resetting.")
    except signing.BadSignature:
        raise PreviewTokenError("preview_invalid", "The preview token is invalid. Preview again.")
    if data.get("puid") != user.id:
        raise PreviewTokenError("preview_user_mismatch", "The preview token does not belong to you.")
    jti = data.get("jti", "")
    if not cache.get(_nonce_key(jti)):
        raise PreviewTokenError("preview_used", "This preview was already used or has expired. Preview again.")
    # Consume immediately (single-use).
    cache.delete(_nonce_key(jti))
    if data.get("snap") != snapshot_hash(user):
        raise PreviewTokenError("preview_stale", "The data changed since the preview. Preview again.")
    return data


class DataResetPreviewView(APIView):
    """Read-only preview: per-model counts, preserved user, config, + a token."""

    permission_classes = [IsSuperAdmin]
    throttle_classes = [DangerZoneThrottle]

    def get(self, request):
        try:
            preview = preview_crm_reset(preserved_user=request.user)
        except ResetError as exc:
            return danger.error(exc.message, exc.code, 400)
        token = issue_preview_token(request.user, preview["snapshot"])
        expires_at = timezone.now() + timedelta(seconds=PREVIEW_TTL_SECONDS)
        record_event(
            action="data_reset.previewed",
            category=AuditCategory.SECURITY,
            user=request.user,
            request=request,
            summary="Full CRM reset previewed.",
            metadata={"total_rows": preview["total_rows"], "other_users": preview["other_users_to_delete"]},
        )
        # Do not expose the internal snapshot fingerprint to the client body.
        body = {k: v for k, v in preview.items() if k != "snapshot"}
        body["preview_token"] = token
        body["preview_expires_at"] = expires_at.isoformat()
        body["confirmation_phrase"] = CONFIRMATION_PHRASE
        return Response(body)


class DataResetExecuteView(APIView):
    """Execute the full reset after every server-side check passes."""

    permission_classes = [IsSuperAdmin]
    throttle_classes = [DangerZoneThrottle]

    def post(self, request):
        # 1) Re-authenticate + exact confirmation phrase.
        guard = (
            danger.check_password(request)
            or danger.check_confirmation(request, CONFIRMATION_PHRASE)
        )
        if guard is not None:
            return guard

        # 2) preserved_user_id must equal the caller.
        guard = danger.check_id_matches(request, "preserved_user_id", request.user.id)
        if guard is not None:
            # A mismatched preserved id is a hard stop — you may only preserve yourself.
            return danger.error(
                "preserved_user_id must equal your own user id.", "preserved_user_mismatch", 400
            )

        # 3) Fresh, valid, single-use preview token bound to the current snapshot.
        try:
            consume_preview_token(request.data.get("preview_token", ""), request.user)
        except PreviewTokenError as exc:
            return danger.error(exc.message, exc.code, 400)

        # 4) Execute (transactional + advisory-locked inside the service).
        try:
            result = reset_crm_data(preserved_user=request.user)
        except ResetConflict as exc:
            return danger.error(exc.message, exc.code, 409)
        except ResetError as exc:
            return danger.error(exc.message, exc.code, 400)

        record_event(
            action="data_reset.executed",
            category=AuditCategory.SECURITY,
            user=request.user,
            request=request,
            summary="Full CRM reset executed; superadmin preserved.",
            metadata={"total_deleted": result["total_deleted"]},
        )
        return Response(
            {
                "detail": "CRM data reset completed. Your account was preserved.",
                "preserved_user": result["preserved_user"],
                "deleted": result["deleted"],
                "total_deleted": result["total_deleted"],
                "reseeded_config": result["reseeded_config"],
            }
        )
