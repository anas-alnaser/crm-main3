"""Server-side off-shift mutation blocking.

A shift-required employee may read the CRM while off shift but may not make
business changes. This is enforced here, on the server — a disabled button in
the UI is never sufficient. Users without an active shift-required policy
(most admins, and anyone not yet enrolled) are unaffected.
"""
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS, BasePermission

from . import services


class OffShiftDenied(PermissionDenied):
    default_detail = "You are off shift. Start your shift to make changes."
    default_code = "off_shift"


class ShiftRequiredForWrite(BasePermission):
    """Allow reads always; allow writes only when a shift-required employee has
    an active work session. Reconciles the session first so an already-expired
    shift blocks the write."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if not services.is_shift_required(user):
            return True
        # Close a silently-expired session before deciding.
        services.reconcile_active_session(user, request=request)
        if services.active_session(user) is not None:
            return True
        raise OffShiftDenied()
