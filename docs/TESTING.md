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

Covered: API client (pagination unwrap, token refresh, error surfacing) and the
AI command bar (server confirmation, blocked feedback, undo, config errors).

## CI

`.github/workflows/ci.yml` runs the backend checks/tests (SQLite + a PostgreSQL
integration job), the frontend typecheck/lint/test/build, and builds both
container images on every push and PR.
