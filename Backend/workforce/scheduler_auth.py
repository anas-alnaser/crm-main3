"""Authenticate the internal work-session reconciliation endpoint.

Google Cloud Scheduler calls it once a minute with a Google-signed OIDC ID token
in the ``Authorization: Bearer`` header. The token is verified with Google's
official library — ``google.oauth2.id_token.verify_oauth2_token`` — which
cryptographically checks the signature against Google's published certificates,
the audience, the expiry, and that the issuer is Google. On top of that we
explicitly enforce the caller identity:

* the issuer is a recognised Google issuer,
* ``email`` equals ``WORKFORCE_SCHEDULER_SERVICE_ACCOUNT``,
* ``email_verified`` is true.

Nothing from the request body or query is ever trusted — the endpoint only
decides *who is calling*, never *what to do*. A normal user's app JWT, an admin's
browser session, and anonymous requests all fail and are rejected.

Security notes:

* We never log, store, or echo the token or Authorization header. Callers log
  only a coarse, non-sensitive rejection *category* (see ``error_status``).
* Google's certificates are fetched through a process-local caching transport
  (:class:`_CachingRequest`) that honours the response ``Cache-Control`` max-age,
  so the one-minute cadence does not refetch certificates every call.
* Verification failures never fail open: any unexpected error (including a cert
  fetch/transport failure) is treated as a rejection, not an authorisation.

``verify_oidc_token`` is the seam mocked by tests so the suite never calls Google.
"""
from __future__ import annotations

import threading
import time

from django.conf import settings

# Recognised Google OIDC issuers for service-account ID tokens.
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")

# HTTP status per rejection category. Anything not listed is a token problem
# (bad signature / audience / issuer / service account / expiry ...) -> 403.
_ERROR_STATUS = {
    "missing_token": 401,
    "not_configured": 503,
    "verification_unavailable": 503,
}


class SchedulerAuthError(Exception):
    """Rejection of a scheduler request.

    ``code`` is a non-sensitive category safe to log; it never contains token
    content. ``message`` is a generic, caller-facing string.
    """

    def __init__(self, code: str, message: str = "Invalid scheduler token."):
        super().__init__(message)
        self.code = code
        self.message = message


def error_status(code: str) -> int:
    """HTTP status for a rejection category (defaults to 403)."""
    return _ERROR_STATUS.get(code, 403)


# --- configuration ----------------------------------------------------------

def _setting(name: str) -> str:
    return (getattr(settings, name, "") or "").strip()


def _required_setting(name: str) -> str:
    value = _setting(name)
    if not value:
        raise SchedulerAuthError(
            "not_configured", "The scheduler reconciliation endpoint is not configured."
        )
    return value


# --- request parsing --------------------------------------------------------

def _extract_bearer_token(request) -> str:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise SchedulerAuthError("missing_token", "Missing bearer token.")
    return parts[1]


# --- Google certificate transport with process-local caching ----------------

_verifier_request = None
_verifier_lock = threading.Lock()


def _max_age_seconds(headers) -> int:
    """Seconds a cert response may be cached, from its Cache-Control/Age headers.

    Returns 0 (do not cache) when no positive ``max-age`` is present.
    """
    if not headers:
        return 0
    get = getattr(headers, "get", None)
    if get is None:
        return 0
    cache_control = get("Cache-Control") or get("cache-control") or ""
    max_age = 0
    for part in str(cache_control).split(","):
        part = part.strip().lower()
        if part.startswith("max-age="):
            try:
                max_age = int(part.split("=", 1)[1])
            except ValueError:
                max_age = 0
    if max_age <= 0:
        return 0
    age = 0
    age_header = get("Age") or get("age")
    if age_header is not None:
        try:
            age = int(age_header)
        except (TypeError, ValueError):
            age = 0
    return max(0, max_age - max(0, age))


class _CachingRequest:
    """A google-auth transport ``Request`` that caches GET responses (Google's
    certificate endpoint) process-locally, honouring their Cache-Control max-age.

    This avoids refetching Google's certificates on every one-minute scheduler
    call. Nothing is persisted to disk; the cache is per-process and in-memory.
    """

    def __init__(self, inner):
        self._inner = inner
        self._lock = threading.Lock()
        self._cache: dict = {}

    def __call__(self, url, method="GET", body=None, headers=None, **kwargs):
        cacheable = method == "GET" and not body
        if cacheable:
            with self._lock:
                entry = self._cache.get(url)
                if entry is not None and entry[0] > time.monotonic():
                    return entry[1]
        response = self._inner(url, method=method, body=body, headers=headers, **kwargs)
        if cacheable and getattr(response, "status", None) == 200:
            ttl = _max_age_seconds(getattr(response, "headers", None))
            if ttl > 0:
                with self._lock:
                    self._cache[url] = (time.monotonic() + ttl, response)
        return response


def _get_verifier_request():
    global _verifier_request
    if _verifier_request is None:
        with _verifier_lock:
            if _verifier_request is None:
                import requests as _requests
                from google.auth.transport import requests as ga_requests

                session = _requests.Session()
                _verifier_request = _CachingRequest(ga_requests.Request(session=session))
    return _verifier_request


# --- verification -----------------------------------------------------------

def verify_oidc_token(token: str, audience: str) -> dict:
    """Cryptographically verify a Google OIDC ID token and return its claims.

    Uses Google's official verifier: checks the RS256 signature against Google's
    certificates, the audience, the expiry, and the Google issuer. Raises
    ``ValueError`` for a bad token and other exceptions for transport/cert
    failures. Mocked in tests so no live Google call is made.
    """
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(token, _get_verifier_request(), audience)


def _categorize_value_error(exc: ValueError) -> str:
    """Map a verifier ValueError to a non-sensitive category (logging only)."""
    msg = str(exc).lower()
    if "expired" in msg:
        return "expired_token"
    if "audience" in msg:
        return "wrong_audience"
    if "issuer" in msg:
        return "wrong_issuer"
    if "signature" in msg:
        return "invalid_signature"
    if "segment" in msg or "malformed" in msg or "wrong number" in msg or "could not" in msg:
        return "malformed_token"
    return "invalid_token"


def _enforce_identity(claims: dict, expected_email: str) -> None:
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise SchedulerAuthError("wrong_issuer")
    verified = claims.get("email_verified", False)
    if verified is not True and str(verified).strip().lower() != "true":
        raise SchedulerAuthError("unverified_email")
    email = (claims.get("email") or "").strip().lower()
    if not email or email != expected_email.strip().lower():
        raise SchedulerAuthError("wrong_service_account")


def authenticate_scheduler(request) -> dict:
    """Return the verified OIDC claims, or raise :class:`SchedulerAuthError`.

    Never trusts unverified claims: the identity checks below run only on the
    output of the cryptographic verifier.
    """
    audience = _required_setting("WORKFORCE_SCHEDULER_AUDIENCE")
    expected_email = _required_setting("WORKFORCE_SCHEDULER_SERVICE_ACCOUNT")
    token = _extract_bearer_token(request)
    try:
        claims = verify_oidc_token(token, audience)
    except SchedulerAuthError:
        raise
    except ValueError as exc:
        # Bad signature / audience / expiry / issuer / malformed token.
        raise SchedulerAuthError(_categorize_value_error(exc)) from None
    except Exception:
        # Certificate fetch/transport failure, verifier unavailable, etc.
        # Reject safely — never fail open.
        raise SchedulerAuthError(
            "verification_unavailable", "Token verification is temporarily unavailable."
        ) from None
    _enforce_identity(claims, expected_email)
    return claims
