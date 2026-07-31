"""Recursive redaction of sensitive values before they are persisted.

The audit log must never store passwords, tokens, connection strings, or
authorization headers. Rather than trust each call site, every metadata /
old-value / new-value payload passes through :func:`redact` first.
"""
from __future__ import annotations

REDACTED = "***redacted***"

# Substrings that, when present in a field name (case-insensitive), mean the
# value must never be stored. Kept broad on purpose.
SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "secret_key",
    "private_key",
    "jwt",
    "refresh",
    "access_token",
    "database_url",
    "connection_string",
    "dsn",
    "sslmode_password",
    "credential",
    "session_key",
    "csrf",
    "signature_key",
    "otp",
)

# Keys that legitimately carry the word "token"/"key" but are safe to keep.
SAFE_KEY_WHITELIST = {
    "token_count",
    "public_key_id",
}

_MAX_DEPTH = 8
_MAX_STRING = 2000


def _is_sensitive(key: str) -> bool:
    lowered = key.lower()
    if lowered in SAFE_KEY_WHITELIST:
        return False
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def redact(value, _depth: int = 0):
    """Return a copy of ``value`` with sensitive fields masked.

    - dict: keys whose name looks sensitive have their value replaced; other
      values are redacted recursively.
    - list/tuple: each item is redacted recursively.
    - str: truncated to a sane maximum so a stray large blob can't bloat a row.
    - other JSON scalars: returned unchanged.
    """
    if _depth > _MAX_DEPTH:
        return REDACTED

    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_str = str(key)
            if _is_sensitive(key_str):
                cleaned[key_str] = REDACTED
            else:
                cleaned[key_str] = redact(item, _depth + 1)
        return cleaned

    if isinstance(value, (list, tuple)):
        return [redact(item, _depth + 1) for item in value]

    if isinstance(value, str):
        return value if len(value) <= _MAX_STRING else value[:_MAX_STRING] + "…"

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    # Fallback: stringify unknown objects (e.g. Decimal, datetime) safely.
    text = str(value)
    return text if len(text) <= _MAX_STRING else text[:_MAX_STRING] + "…"
