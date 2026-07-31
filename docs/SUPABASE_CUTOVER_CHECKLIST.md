# Supabase PostgreSQL — Setup & Cutover Checklist

Django's ORM remains the **single authority** over the schema and migrations.
Supabase is only the PostgreSQL **host**. React always talks to Django — never to
Supabase directly, no Supabase Auth, no Supabase JS libraries.

## Architecture (unchanged)

```
React/Vite  →  Django REST Framework  →  Django ORM  →  Supabase-hosted PostgreSQL
```

## Secrets rule

The real connection URI lives **only** in `Backend/.env.supabase.local`, which is
git-ignored. Never print it, commit it, put it in tests/Dockerfiles/CI, or send
it to the frontend. `redact_database_url()` masks username/password in every
diagnostic. `Backend/.env.supabase.example` is a **secret-free** template that is
safe to commit.

## Connection modes

- **Session Pooler, port 5432** — the normal persistent Django runtime
  connection. Set as `DATABASE_URL`.
- **Direct connection, port 5432** — preferred for migrations/backups once IPv6
  is confirmed. Set as `DATABASE_MIGRATION_URL`; select it with
  `DJANGO_DB_TARGET=migration`.
- **Do NOT** use the transaction pooler (port 6543) as the default persistent
  Django connection.
- SSL is required (`DATABASE_SSLMODE=require`).

## 1. Configure locally (no secrets committed)

- [ ] `cp Backend/.env.supabase.example Backend/.env.supabase.local`
- [ ] Paste the real Session Pooler URI into `DATABASE_URL` in that local file.
- [ ] Confirm it is ignored: `git check-ignore Backend/.env.supabase.local`
      → prints the path (good).

## 2. Validate the connection safely (no schema changes)

```bash
cd Backend
python manage.py check_supabase --health-check
```

This connects **directly with psycopg** (never through Django's default
connection), prints a **redacted** target, the server version, database name,
timezone, and accessible schemas, lists existing tables, and runs a transient
`CREATE TEMP TABLE` read/write/sequence/timezone probe that cleans itself up.

- [ ] Connection succeeds; server version and database name look right.
- [ ] `public` schema is **empty** or contains **only Django-owned tables**.
- [ ] If unknown/unrelated application tables are present → **stop**, do not
      migrate, report the finding.

## 3. Apply migrations through Django (Django owns the schema)

```bash
cd Backend
DJANGO_ENV_FILE=.env.supabase.local python manage.py showmigrations
DJANGO_ENV_FILE=.env.supabase.local python manage.py migrate --plan
# Review the plan, then:
DJANGO_ENV_FILE=.env.supabase.local python manage.py migrate
```

- [ ] Never use `--fake` / `--fake-initial`.
- [ ] Never create Django-controlled tables by hand in the Supabase Table Editor.
- [ ] After migrating: `showmigrations` shows all applied; expected Django tables
      exist; a safe read/write health check passes; sequences and timezone behave.

## 4. Data migration (only if there is existing data)

Detect the current source (SQLite `db.sqlite3`, local PostgreSQL, or another
instance). **Do not delete it.** Do **not** upload a SQLite file directly into
PostgreSQL — use a Django-aware method.

Backup → export → import → verify → (rollback if needed):

```bash
# 1. Back up the current (source) database first.
#    SQLite:      cp db.sqlite3 db.sqlite3.backup-$(date +%F)
#    PostgreSQL:  pg_dump "$SOURCE_URL" > backup-$(date +%F).sql   (see docs/BACKUP.md)

# 2. Export application data from the source (natural keys, UTF-8):
python manage.py dumpdata --natural-primary --natural-foreign \
  --exclude contenttypes --exclude auth.permission --indent 2 > data.json

# 3. Import into the freshly-migrated Supabase database:
DJANGO_ENV_FILE=.env.supabase.local python manage.py loaddata data.json

# 4. Verify (record counts, FKs, users, deals/sales, archives, AI logs).
```

- [ ] Record counts match per model (users, clients, deals, meetings, etc.).
- [ ] Foreign keys resolve; no orphans.
- [ ] Deals + sales calculations (commission, leaderboard, won-this-month) match.
- [ ] Archived records, AI command logs preserved.
- [ ] A backup + verification report exists **before** the final cutover.

## 5. Cutover

- [ ] Point the running service at `DATABASE_URL` (Session Pooler).
- [ ] Smoke test: health check, login, start/end shift, leads, workforce, audit,
      brand pages, static/media, SPA refresh.

## 6. Rollback

- [ ] Set `DATABASE_URL` back to the previous database (or clear it to use the
      local `POSTGRES_*` / SQLite path) and restart. The old source database was
      never deleted, so rollback is immediate.

## 7. Supabase Data API hardening (production)

React uses Django, so the Supabase Data API must not expose CRM tables. Choose
one:

- [ ] **Disable the Supabase Data API** for the project, or
- [ ] Ensure the `anon` and `authenticated` roles have **no access** to
      Django-owned tables. Do **not** create public RLS policies for CRM tables.

## Never

- [ ] Never run the automated **test suite** against the shared Supabase dev
      project (tests use isolated local SQLite / PostgreSQL).
- [ ] Never run destructive SQL, drop schemas/databases, or `flush`.
