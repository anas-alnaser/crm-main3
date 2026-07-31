"""Authenticate the internal work-session reconciliation endpoint.

The reconciliation endpoint is invoked only by a Google Cloud Scheduler job, once
a minute, over the public internet (Cloud Run must stay publicly reachable so the
browser SPA can call the rest of the API). It therefore authenticates the caller
at the application layer using the **verified OIDC token** that Cloud Scheduler
attaches to the request:

1. The request must carry ``Authorization: Bearer <jwt>``.
2. The JWT is verified against Google's public signing keys (RS256), with the
   audience pinned to our configured value and ``exp``/``iat`` enforced.
3. The verified token must be issued by Google (``iss``) for the specific
   scheduler service account (``email`` + ``email_verified``) we expect.

No user id, timestamp, or any other value from the request body/query is trusted
— the endpoint only decides *who is calling*, never *what to do* (it always runs
the same idempotent, server-clock sweep). A normal user's SimpleJWT, an admin's
browser session, and anonymous requests all fail step 1–3 and are rejected.

The signature/audience verification (:func:`verify_oidc_token`) is a module-level
seam so tests can inject deterministic claims without a network round-trip; the
identity enforcement below always runs against those claims.
"""
from __future__ import annotations

from django.conf import settings

# Google mints service-account ID tokens under these issuers.
GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")
GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"

# Cache the fetched JWK set for an hour; Google rotates keys roughly daily and
# with one call per minute this keeps network chatter negligible.
_JWKS_CACHE_LIFESPAN_SECONDS = 3600

_jwks_client = None


class SchedulerAuthError(Exception):
    """Rejection of a scheduler request. ``code`` maps to an HTTP status."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _setting(name: str) -> str:
    return (getattr(settings, name, "") or "").strip()


def _required_setting(name: str) -> str:
    value = _setting(name)
    if not value:
        raise SchedulerAuthError(
            "not_configured",
            "The scheduler reconciliation endpoint is not configured.",
        )
    return value


def _extract_bearer_token(request) -> str:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise SchedulerAuthError("missing_token", "Missing bearer token.")
    return parts[1]


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        import jwt

        _jwks_client = jwt.PyJWKClient(
            GOOGLE_CERTS_URL, lifespan=_JWKS_CACHE_LIFESPAN_SECONDS
        )
    return _jwks_client


def verify_oidc_token(token: str, audience: str) -> dict:
    """Verify a Google-signed OIDC token's signature, audience, and expiry.

    Returns the decoded claims. Raises for any cryptographic/validation failure.
    Patched in tests to avoid a live call to Google's certificate endpoint.
    """
    import jwt

    signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        options={"require": ["exp", "iat", "aud", "iss"]},
    )


def _enforce_identity(claims: dict, expected_email: str) -> None:
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise SchedulerAuthError("invalid_token", "Untrusted token issuer.")
    if not claims.get("email_verified", False):
        raise SchedulerAuthError("invalid_token", "Token email is not verified.")
    email = (claims.get("email") or "").strip().lower()
    if not email or email != expected_email.strip().lower():
        raise SchedulerAuthError("invalid_token", "Token subject is not permitted.")


def authenticate_scheduler(request) -> dict:
    """Return the verified OIDC claims, or raise :class:`SchedulerAuthError`."""
    audience = _required_setting("WORKFORCE_SCHEDULER_AUDIENCE")
    expected_email = _required_setting("WORKFORCE_SCHEDULER_SERVICE_ACCOUNT")
    token = _extract_bearer_token(request)
    try:
        claims = verify_oidc_token(token, audience)
    except SchedulerAuthError:
        raise
    except Exception:
        # Bad signature, wrong audience, expired, malformed, unknown key, etc.
        raise SchedulerAuthError("invalid_token", "Invalid scheduler token.")
    _enforce_identity(claims, expected_email)
    return claims
