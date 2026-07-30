from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """Throttle login attempts by client IP to slow credential stuffing."""

    scope = "login"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class AICommandThrottle(ScopedRateThrottle):
    """Per-user throttle for the (paid) AI command endpoints."""

    scope_attr = "throttle_scope"
