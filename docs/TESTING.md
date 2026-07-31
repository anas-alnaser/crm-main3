# Testing

## Backend (Django test framework)

```bash
cd Backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

python manage.py test                 # run all tests
coverage run manage.py test           # with coverage
coverage report                       # text coverage summary
ruff check .                          # lint
python manage.py check                # system checks
python manage.py check --deploy       # production readiness checks
python manage.py makemigrations --check --dry-run   # migration drift
```

Coverage lives in `pyproject.toml`. Tests use an in-memory SQLite database and a
shared base (`crm/apitestbase.py`) that clears the throttle cache between tests.

### What is covered
Auth (login/refresh/me), user administration (create/role/deactivate/reactivate/
reset, last-admin & self-deactivation guards), ownership permissions for
clients/projects/tasks/activities, company archive/restore, deal permissions &
value masking, owner-lock, won/lost/reopen + `closed_at`, commission,
leaderboard periods & masking, dashboard, pipeline/stage protected deletes,
pagination, global search masking, health, and the full AI command flow
(tier routing, confirmation preview/consume/replay/expiry/foreign-user,
blocked/unknown/low-confidence/missing/ambiguous no-ops, undo, throttling,
provider-error non-leakage). AI tests mock the provider — no network is needed.

**Workforce** (`workforce/tests.py`, `workforce/test_metrics.py`): policy defaults
(Sun–Thu), start-shift window rules (before-9AM/at-9AM/before-9PM/at-9PM/
disallowed-day/exception-day/holiday/inactive), duplicate-active & partial-unique
constraint, multiple sessions, overtime, manual end + preview totals, ten-minute
inactivity crediting, last-activity+10 math, 9 PM hard cap, inactivity capped at
9 PM, reconciliation idempotency, scheduled `close_stale_work_sessions`, laptop-
disappearance, late-heartbeat closure, off-shift mutation denial/read-only/admin-
exemption, admin close, foreign-session rejection, and the metrics dashboard.

**Audit** (`audit/tests.py`): recursive secret redaction, event recording,
shift/CRUD/lead audit trails, admin-only viewer, category filter, CSV export,
privacy notice, telemetry whitelist accept/reject/de-duplicate.

**Leads** (`leads/tests.py`): phone normalization & duplicate collision, Excel
parse (valid/missing-headers/missing-name/invalid-phone/duplicate-in-file/
duplicate-existing/formula-cell/empty-rows), upload API (admin assign, preview,
sales-denied, bad-extension), scoping (sales-only-assigned, foreign 404),
contact attempts (no-answer, follow-up-requires-date, off-shift denial), delete
disabled, overdue filter, and conversion (create client / with deal / duplicate
prevented / not-interested blocked / no-answer-needs-reason / existing-client
link / admin reopen with reason / atomic).

**Branding** (`branding/tests.py`): seed structure, Morph brands share a legal
entity, Fuel separate, no fabricated identifiers, generation + snapshot, per-brand
prefixes, unique incrementing numbers, shared Morph sequence, snapshot immutable
to later brand edits, historical Fuel stays Fuel, admin-only modification, generate
API, unique-number constraint.

**Database config** (`crm/tests.py`): credential redaction, SSL/conn-age applied
from `DATABASE_URL`, production requires a database, dev SQLite fallback, no forced
SSL for local `POSTGRES_*`.

Tests use isolated local SQLite (or the PostgreSQL CI job) — **never** the shared
Supabase development project.

## Frontend (Vitest + Testing Library)

```bash
cd Frontend
npm ci
npm run typecheck      # tsc
npm run lint           # eslint
npm run test           # vitest run
npm run test:coverage  # with coverage
npm run build          # production build
```

Covered: API client (pagination unwrap, token refresh, error surfacing), the AI
command bar (server confirmation, blocked feedback, undo, config errors), the
**My Shift** page (start/end/preview, off-shift disable, not-required, inactivity
notice), the **Leads** page (admin-only upload, sales scoping, not-interested red
styling, telemetry on open), the **Workforce** dashboard (employee select, metrics
render, inactivity observation), and **Brand Profiles** (brand list, incomplete-
legal warning, brand-selector document generation + snapshot).

## CI

`.github/workflows/ci.yml` runs the backend checks/tests (SQLite + a PostgreSQL
integration job), the frontend typecheck/lint/test/build, and builds both
container images on every push and PR.
