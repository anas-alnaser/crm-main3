# Architecture

## Overview

Fueldezign CRM is a decoupled single-page app + REST API.

- **Backend** — Django 5 + Django REST Framework, JWT auth (SimpleJWT), Django
  admin (Unfold). SQLite for local dev, PostgreSQL for production.
- **Frontend** — React 18 + Vite + TypeScript, TanStack Query/Table, React
  Router, React Hook Form + Zod, Tailwind CSS.

```
Browser ──HTTP──> nginx (frontend container)
                     ├── / , /assets  → static SPA (React build)
                     └── /api, /admin, /static → proxy → gunicorn (backend) → PostgreSQL
```

In development the SPA runs on Vite (`:5173`) and calls the API on `:8000`
directly (CORS allow-listed).

## Backend apps

| App | Responsibility |
| --- | --- |
| `accounts` | Custom `User` (admin/sales roles), auth, user administration |
| `clients` | Companies (soft-delete/archive, ownership) |
| `projects` | Delivery projects (ownership) |
| `tasks` | Tasks (ownership) |
| `activities` | Activity log (ownership) |
| `meetings` | Meetings/schedule (owner-scoped) |
| `sales` | Pipelines, stages, deals, commission, leaderboard |
| `ai_commands` | Natural-language admin commands + confirmation/undo |
| `workforce` | Employee work policies, shifts/sessions, presence, inactivity, metrics dashboard |
| `leads` | Excel lead import, phone normalization, contact attempts, conversion |
| `audit` | Server-authoritative audit events, redaction, telemetry whitelist, viewer |
| `branding` | Legal entities, brand profiles, signatories, document numbering + snapshots |
| `crm` | Settings, URLs, dashboard, health, global search, DB config, imaging, shared utilities |

## Request flow (frontend)

Component → TanStack Query hook → `src/api/client.ts` (`apiRequest`/`fetchList`)
→ adds `Authorization: Bearer <access>` from `localStorage`, auto-refreshes on
401 → DRF viewset → serializer → ORM → response → query-cache invalidation →
re-render + toast.

## Database (Supabase-hostable PostgreSQL)

`crm/dbconfig.py` builds the connection from the environment. Resolution order:
`DATABASE_URL` (Supabase Session Pooler on port 5432 — the persistent Django
runtime connection) → the individual `POSTGRES_*` variables (local/Docker) →
SQLite (**development only**). Production (`DEBUG=False`) **requires** PostgreSQL
and never silently falls back to SQLite. Supabase connections require SSL
(`DATABASE_SSLMODE=require`). `DATABASE_MIGRATION_URL` (selected with
`DJANGO_DB_TARGET=migration`) is preferred for migrations/backups. Credentials
are always redacted in diagnostics; the browser never talks to Supabase directly.
See [Supabase cutover](SUPABASE_CUTOVER_CHECKLIST.md).

## Cross-cutting

- **Pagination** — page-number pagination (`{count,next,previous,page,page_size,total_pages,results}`), `page_size` capped at 200.
- **Throttling** — per-user, per-anon, login (per-IP), and AI (per-user) scopes.
- **Permissions** — role checks + object-level ownership (`created_by`/`owner`); shift-required employees are blocked from mutations while off shift (`workforce.permissions.ShiftRequiredForWrite`).
- **Timezone** — timestamps stored UTC; shift/business logic uses `BUSINESS_TIMEZONE` (Asia/Amman).
- **Audit** — meaningful server events recorded via `audit.services.record_event`; sensitive fields redacted before storage.
- **Scheduler** — `close_stale_work_sessions` (idempotent) run ~once/min by a lightweight container/cron; no Redis/Celery.
- **Security** — production settings enable HSTS, SSL redirect, secure cookies, nosniff, referrer-policy, X-Frame-Options.
