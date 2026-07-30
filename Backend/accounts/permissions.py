from rest_framework.permissions import SAFE_METHODS, BasePermission


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
