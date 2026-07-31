"""Safe, read-mostly validation of a Supabase (or any) PostgreSQL connection.

This command connects **directly with psycopg** using the URL from a local,
git-ignored env file (default ``.env.supabase.local``) — it never routes through
Django's configured ``default`` connection and never mutates Django-owned
tables. Credentials are always redacted before printing.

    python manage.py check_supabase
    python manage.py check_supabase --health-check
    python manage.py check_supabase --env-file .env.supabase.local

What it reports (Phase 1.3):
  * a redacted view of the connection target (host/port/db only),
  * server version, current database, and accessible schemas,
  * existing tables (to confirm the project is empty or Django-only),
  * with --health-check: a transient CREATE TEMP TABLE round-trip that verifies
    read/write, sequence, and timezone behaviour and cleans itself up.

It intentionally does not run migrations or the test suite. Never point the
automated test runner at the shared Supabase project.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from crm.dbconfig import redact_database_url

SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}
SUPABASE_SCHEMAS = {"auth", "storage", "extensions", "graphql", "graphql_public", "realtime", "supabase_functions", "vault", "pgsodium", "pgsodium_masks", "net", "cron", "_realtime", "supabase_migrations"}
DJANGO_TABLE_PREFIXES = (
    "django_", "auth_", "accounts_", "clients_", "projects_", "sales_", "tasks_",
    "activities_", "meetings_", "ai_commands_", "audit_", "workforce_", "leads_", "branding_",
    "token_blacklist_",
)


def _read_env_file(path: Path) -> dict:
    values = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


class Command(BaseCommand):
    help = "Validate a Supabase/PostgreSQL connection safely (credentials redacted)."

    def add_arguments(self, parser):
        parser.add_argument("--env-file", default=".env.supabase.local")
        parser.add_argument("--health-check", action="store_true", help="Run a transient read/write/sequence/timezone probe.")

    def handle(self, *args, **options):
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - psycopg is a hard dep
            raise CommandError(f"psycopg is required: {exc}")

        env_path = Path(settings.BASE_DIR) / options["env_file"]
        values = _read_env_file(env_path)
        # Prefer the migration/direct URL for validation, fall back to runtime.
        url = values.get("DATABASE_MIGRATION_URL") or values.get("DATABASE_URL")
        if not url:
            raise CommandError(
                f"No DATABASE_URL or DATABASE_MIGRATION_URL found in {options['env_file']}. "
                "This file is git-ignored; create it locally with your Supabase Session Pooler URI."
            )

        sslmode = values.get("DATABASE_SSLMODE", "require")
        self.stdout.write(f"Connection target: {redact_database_url(url)}")
        self.stdout.write(f"SSL mode: {sslmode}")

        conninfo = url
        if "sslmode=" not in url:
            conninfo = f"{url}{'&' if '?' in url else '?'}sslmode={sslmode}"

        try:
            conn = psycopg.connect(conninfo, connect_timeout=10)
        except Exception as exc:  # noqa: BLE001 - report a redacted, friendly error
            # Never echo the URL back in the error.
            raise CommandError(f"Could not connect: {type(exc).__name__}: {self._safe_error(exc, url)}")

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version(), current_database(), current_setting('TIMEZONE'), now()")
                version, database, tz, now = cur.fetchone()
                self.stdout.write(self.style.SUCCESS("Connected."))
                self.stdout.write(f"  Server: {version.split(',')[0]}")
                self.stdout.write(f"  Database: {database}")
                self.stdout.write(f"  Server timezone: {tz}")
                self.stdout.write(f"  Server now(): {now}")

                cur.execute(
                    "SELECT schema_name FROM information_schema.schemata ORDER BY schema_name"
                )
                schemas = [r[0] for r in cur.fetchall()]
                app_schemas = [s for s in schemas if s not in SYSTEM_SCHEMAS and s not in SUPABASE_SCHEMAS]
                self.stdout.write(f"  Schemas: {', '.join(schemas)}")

                cur.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' ORDER BY table_name"
                )
                public_tables = [r[0] for r in cur.fetchall()]
                django_tables = [t for t in public_tables if t.startswith(DJANGO_TABLE_PREFIXES)]
                unknown_tables = [t for t in public_tables if t not in django_tables]

                self.stdout.write(f"  public tables: {len(public_tables)} "
                                  f"({len(django_tables)} Django-owned, {len(unknown_tables)} other)")
                if unknown_tables:
                    self.stdout.write(self.style.WARNING(
                        "  Non-Django tables found in public schema: " + ", ".join(unknown_tables[:20])
                    ))
                    self.stdout.write(self.style.WARNING(
                        "  Review these before migrating. Do NOT migrate over unrelated application data."
                    ))
                elif not public_tables:
                    self.stdout.write(self.style.SUCCESS("  public schema is empty — safe to migrate a fresh project."))
                else:
                    self.stdout.write(self.style.SUCCESS("  public schema contains only Django-owned tables."))

                if app_schemas:
                    self.stdout.write(f"  Extra non-system schemas: {', '.join(app_schemas)}")

                if options["health_check"]:
                    self._health_check(cur, conn)
        finally:
            conn.close()

        self.stdout.write(self.style.SUCCESS("Validation complete. No credentials were printed."))

    def _health_check(self, cur, conn):
        self.stdout.write("Running transient health check (CREATE TEMP TABLE)...")
        # TEMP tables are session-local and dropped automatically; this never
        # touches Django-owned data.
        cur.execute("CREATE TEMP TABLE crm_healthcheck (id serial PRIMARY KEY, label text, created_at timestamptz DEFAULT now())")
        cur.execute("INSERT INTO crm_healthcheck (label) VALUES ('probe-1'), ('probe-2') RETURNING id")
        ids = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT count(*) FROM crm_healthcheck")
        count = cur.fetchone()[0]
        # Sequence behaviour: the two ids must be consecutive.
        sequence_ok = len(ids) == 2 and ids[1] == ids[0] + 1
        cur.execute("SELECT created_at FROM crm_healthcheck ORDER BY id LIMIT 1")
        ts = cur.fetchone()[0]
        # Delete only the temporary records we created, then drop the temp table.
        cur.execute("DELETE FROM crm_healthcheck")
        cur.execute("SELECT count(*) FROM crm_healthcheck")
        remaining = cur.fetchone()[0]
        cur.execute("DROP TABLE crm_healthcheck")
        conn.rollback()  # discard the temp table entirely; nothing persisted
        self.stdout.write(self.style.SUCCESS(
            f"  read/write OK (inserted {count}, sequence {'OK' if sequence_ok else 'UNEXPECTED'}, "
            f"timezone-aware={ts.tzinfo is not None}, cleaned up {remaining == 0})"
        ))

    @staticmethod
    def _safe_error(exc, url):
        message = str(exc)
        if url in message:
            message = message.replace(url, "<redacted-url>")
        return message
