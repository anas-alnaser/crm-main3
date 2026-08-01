from rest_framework.permissions import SAFE_METHODS, BasePermission


def is_super_admin(user) -> bool:
    """The single, strict definition of a *superadmin*.

    A superadmin is the trusted account allowed to perform irreversible,
    destructive operations (permanent record deletion and the full CRM reset).
    This is deliberately stricter than :attr:`User.is_admin_role`: a normal
    ``role="admin"`` staff user is NOT a superadmin. All five conditions must
    hold — authenticated, active, staff, Django superuser, and CRM admin role.
    """
    return bool(
        user
        and user.is_authenticated
        and user.is_active
        and user.is_staff
        and user.is_superuser
        and getattr(user, "role", None) == "admin"
    )


class IsSuperAdmin(BasePermission):
    """Gate for irreversible, superadmin-only endpoints (permanent delete, reset).

    Frontend visibility is never sufficient — every destructive endpoint enforces
    this on the server. See :func:`is_super_admin` for the exact definition."""

    message = "Only a superadmin can perform this action."

    def has_permission(self, request, view):
        return is_super_admin(request.user)


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_admin_role)


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and request.user.is_authenticated and request.user.is_admin_role)


class DealPermission(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        if request.user.is_admin_role:
            return True
        if request.method in SAFE_METHODS:
            return True
        return obj.owner_id == request.user.id


class IsOwnerOrAdmin(BasePermission):
    """Shared read for all authenticated users; writes limited to admin or the
    record's creator. The owner field defaults to ``created_by`` but a view can
    override it with ``owner_field``.
    """

    default_owner_field = "created_by"

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if request.user.is_admin_role:
            return True
        owner_field = getattr(view, "owner_field", self.default_owner_field)
        return getattr(obj, f"{owner_field}_id", None) == request.user.id
