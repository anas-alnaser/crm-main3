"""Shared guards for irreversible, superadmin-only ("danger zone") endpoints.

Every permanent-delete and full-reset endpoint re-authenticates the actor with
their current password and requires an exact typed confirmation phrase, on the
server. These helpers return a ready-to-send DRF ``Response`` on failure (or
``None`` on success) so each view can short-circuit with a consistent, safe
``{"detail", "code"}`` error body. They never echo the supplied password.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response


def error(detail: str, code: str, http_status: int = status.HTTP_400_BAD_REQUEST) -> Response:
    """A uniform, safe error body the frontend can branch on via ``code``."""
    return Response({"detail": detail, "code": code}, status=http_status)


def check_password(request) -> Response | None:
    """Re-authenticate the actor with their *current* password.

    The password is read from the request body, checked, and never stored,
    logged, or returned.
    """
    password = request.data.get("current_password")
    if not password:
        return error("Your current password is required.", "password_required")
    if not request.user.check_password(password):
        return error("Incorrect password.", "incorrect_password")
    return None


def check_confirmation(request, expected: str) -> Response | None:
    """Require the exact typed confirmation phrase (e.g. ``DELETE LEAD``)."""
    value = request.data.get("confirmation")
    if value != expected:
        return error(
            f'The confirmation phrase must be typed exactly: "{expected}".',
            "confirmation_mismatch",
        )
    return None


def check_id_matches(request, field: str, expected_id: int) -> Response | None:
    """Require the body's target id to match the URL object, defeating a stale
    or swapped target (e.g. deleting a different lead than the one reviewed)."""
    raw = request.data.get(field)
    if raw is None:
        return error(f"'{field}' is required and must match the target.", "id_required")
    try:
        supplied = int(raw)
    except (TypeError, ValueError):
        return error(f"'{field}' must be a number matching the target.", "id_invalid")
    if supplied != int(expected_id):
        return error(
            "The confirmed id does not match the record being deleted.",
            "id_mismatch",
        )
    return None
