"""Database configuration and credential-safe diagnostics.

Django ORM remains the single authority over the schema; Supabase is only the
PostgreSQL *host*. This module builds the ``DATABASES`` mapping from the
environment and provides redaction helpers so a connection string is never
logged or surfaced in full.

Resolution order for the ``default`` connection:

1. ``DATABASE_URL`` — the normal runtime connection (Supabase Session Pooler on
   port 5432 is valid for this persistent Django service). When
   ``DJANGO_DB_TARGET=migration`` is set, ``DATABASE_MIGRATION_URL`` is used
   instead (preferred for migrations/backups, e.g. the direct connection).
2. The individual ``POSTGRES_*`` variables — the local/Docker PostgreSQL path,
   preserved for backward compatibility. No SSL is forced here.
3. SQLite fallback — **development only**. In production (``DEBUG=False``) an
   absent PostgreSQL configuration is a hard error; Django never silently falls
   back to SQLite where real data lives.
"""
from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import dj_database_url


class DatabaseConfigurationError(RuntimeError):
    """Raised when the runtime database configuration is unsafe or missing."""


def redact_database_url(url: str | None) -> str:
    """Return ``url`` with any username and password masked.

    ``postgresql://user:secret@host:5432/db`` -> ``postgresql://u***:***@host:5432/db``

    Safe to log or include in diagnostics: the host, port, and database name are
    preserved (useful for verification) while credentials are never revealed.
    """
    if not url:
        return "(not set)"
    try:
        parts = urlsplit(url)
    except ValueError:
        return "(unparseable url — redacted)"

    if not parts.netloc:
        # No authority component (e.g. sqlite path); nothing credential-like.
        return url

    userinfo = ""
    if parts.username:
        userinfo = parts.username[0] + "***"
    if parts.password:
        userinfo = f"{userinfo}:***" if userinfo else "***"

    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    netloc = f"{userinfo}@{host}" if userinfo else host
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _apply_postgres_tuning(config: dict, *, sslmode: str | None, conn_max_age: int) -> dict:
    """Attach SSL and connection-lifetime settings to a PostgreSQL config."""
    engine = config.get("ENGINE", "")
    if "postgresql" in engine:
        config["CONN_MAX_AGE"] = conn_max_age
        if sslmode:
            options = dict(config.get("OPTIONS") or {})
            options.setdefault("sslmode", sslmode)
            config["OPTIONS"] = options
    return config


def build_database_config(env, *, debug: bool) -> dict:
    """Build the ``DATABASES['default']`` mapping from the environment.

    ``env`` is a callable ``env(name, default=None)`` (the settings helper).
    """
    conn_max_age = int(env("DATABASE_CONN_MAX_AGE", "60"))
    sslmode = env("DATABASE_SSLMODE", "require")

    target = (env("DJANGO_DB_TARGET", "runtime") or "runtime").strip().lower()
    runtime_url = env("DATABASE_URL")
    migration_url = env("DATABASE_MIGRATION_URL")

    # Prefer the migration/backup connection only when explicitly targeted and
    # actually supplied; otherwise always use the runtime URL.
    if target == "migration" and migration_url:
        chosen_url = migration_url
    else:
        chosen_url = runtime_url

    if chosen_url:
        config = dj_database_url.parse(chosen_url, conn_max_age=conn_max_age)
        return _apply_postgres_tuning(config, sslmode=sslmode, conn_max_age=conn_max_age)

    # Backward-compatible individual-variable path (local / Docker PostgreSQL).
    # SSL is NOT forced here: local and in-cluster PostgreSQL commonly have no
    # TLS. Set POSTGRES_SSLMODE explicitly if a networked instance needs it.
    if env("POSTGRES_DB"):
        config = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB"),
            "USER": env("POSTGRES_USER", "postgres"),
            "PASSWORD": env("POSTGRES_PASSWORD", "postgres"),
            "HOST": env("POSTGRES_HOST", "localhost"),
            "PORT": env("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": conn_max_age,
        }
        pg_sslmode = env("POSTGRES_SSLMODE")
        if pg_sslmode:
            config["OPTIONS"] = {"sslmode": pg_sslmode}
        return config

    # No PostgreSQL configured.
    if not debug:
        raise DatabaseConfigurationError(
            "No database configured. Set DATABASE_URL (or the POSTGRES_* variables) "
            "to a PostgreSQL instance when DJANGO_DEBUG=False. Django never falls "
            "back to SQLite in production."
        )

    from pathlib import Path

    base_dir = Path(__file__).resolve().parent.parent
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": base_dir / "db.sqlite3",
    }
