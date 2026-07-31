# Fueldezign CRM Backend

Django REST API. JWT auth; users are created by admins (no public registration).
Python 3.12.

## Setup

```bash
cd Backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt  # runtime-only: requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

SQLite by default (leave `POSTGRES_DB`/`DATABASE_URL` empty). For PostgreSQL set
`DATABASE_URL` (preferred — Supabase Session Pooler works here) or the individual
`POSTGRES_*` variables. Production requires PostgreSQL; it never falls back to
SQLite. All settings are environment-driven — see `.env.example` for the full,
documented list (database/SSL, JWT, throttling, AI, workforce, media, security).

To validate a Supabase connection safely (redacted, no schema changes):

```bash
python manage.py check_supabase --health-check
```

See [../docs/SUPABASE_CUTOVER_CHECKLIST.md](../docs/SUPABASE_CUTOVER_CHECKLIST.md).

## API surface

- Auth: `POST /api/auth/token/` (alias `/login/`), `POST /api/auth/token/refresh/`, `GET /api/auth/me/`
- Resources (paginated, filter/search/order): `/api/clients/`, `/api/projects/`,
  `/api/tasks/`, `/api/activities/`, `/api/meetings/` (+`/upcoming/`),
  `/api/deals/` (+`/{id}/move/`), `/api/pipelines/`, `/api/stages/`, `/api/users/`
  (+`/deactivate/`, `/reactivate/`, `/reset-password/`)
- Sales: `GET /api/dashboard/stats/`, `GET /api/commission/` (+PATCH admin),
  `GET /api/leaderboard/`
- Search: `GET /api/search/?q=` (role-masked)
- Health: `GET /api/health/` (unauthenticated)
- AI (admin): `POST /api/ai/command/`, `/confirm/`, `/cancel/`, `/undo/`
  — see [../docs/AI_COMMANDS.md](../docs/AI_COMMANDS.md)
- Workforce: `GET/POST /api/workforce/shift/status|start|end|end/preview|heartbeat/`,
  `/api/work-policies/`, `/api/work-policy-exceptions/`, `/api/work-sessions/`
  (+`/{id}/close/`), `GET /api/workforce/dashboard/?employee=`, `/employees/`
  — see [../docs/WORKFORCE_POLICY.md](../docs/WORKFORCE_POLICY.md)
- Leads: `/api/leads/` (+`/{id}/contact|attempts|convert|reopen|assign|match-candidates/`),
  `/api/lead-imports/` (+`/upload/`) — see [../docs/LEAD_WORKFLOW.md](../docs/LEAD_WORKFLOW.md)
- Audit (admin): `/api/audit-events/` (+`/export/`, `/privacy-notice/`),
  `POST /api/telemetry/` — see [../docs/AUDIT_LOGGING.md](../docs/AUDIT_LOGGING.md)
- Branding: `/api/legal-entities/`, `/api/brands/` (+`/{id}/logo/`),
  `/api/signatories/` (+`/{id}/signature/`), `/api/documents/` (+`/generate/`)
  — see [../docs/MULTIBRAND_DOCUMENTS.md](../docs/MULTIBRAND_DOCUMENTS.md)

List responses are paginated: `{count,next,previous,page,page_size,total_pages,results}`.

## Scheduled jobs

`python manage.py close_stale_work_sessions` closes work sessions past their
inactivity timeout or the 9:00 PM cap. Idempotent, transaction- and
concurrency-safe. Run ~once per minute in production (the Docker `scheduler`
service, cron, or a systemd timer). `python manage.py seed_acceptance_data`
[`--cleanup`] manages clearly-tagged manual-acceptance data (dev only).

## Quality gates

```bash
ruff check .
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
coverage run manage.py test && coverage report
```

## Admin

`python manage.py createsuperuser`, then open `http://localhost:8000/admin/`.
