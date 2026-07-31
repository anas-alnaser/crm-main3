"""Custom DRF exception handler.

Adds a machine-readable ``code`` to simple ``{"detail": "..."}`` error bodies
(permission, authentication, throttle, not-found) so the frontend can branch on
a stable slug — e.g. ``off_shift`` for off-shift mutation denials. Field
validation errors (whose body is a per-field mapping) are left untouched.
"""
from rest_framework.views import exception_handler as drf_exception_handler


def custom_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return response
    data = response.data
    if isinstance(data, dict) and set(data.keys()) == {"detail"} and hasattr(exc, "get_codes"):
        codes = exc.get_codes()
        if isinstance(codes, str):
            data["code"] = codes
    return response
