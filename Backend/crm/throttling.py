from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """Throttle login attempts by client IP to slow credential stuffing."""

    scope = "login"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class AICommandThrottle(ScopedRateThrottle):
    """Per-user throttle for the (paid) AI command endpoints."""

    scope_attr = "throttle_scope"


class DangerZoneThrottle(SimpleRateThrottle):
    """Per-user throttle for irreversible superadmin endpoints.

    Caps preview attempts, password-failure retries, and execute attempts on the
    permanent-delete and full-reset endpoints to slow brute forcing and misuse.
    Keyed by user id (these endpoints are authenticated superadmin-only)."""

    scope = "danger"

    def get_cache_key(self, request, view):
        ident = request.user.pk if request.user and request.user.is_authenticated else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
