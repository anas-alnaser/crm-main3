# Fueldezign CRM

Private CRM for running Fueldezign, a branding/design/dev agency: companies,
projects, tasks, activities, meetings, and a sales pipeline (deals, commission,
leaderboard), plus an admin-only natural-language AI command bar.

- **Backend** — Django REST Framework API + Django admin, JWT auth, SQLite for
  local dev, PostgreSQL for production.
- **Frontend** — React/Vite/TypeScript dashboard.

There is no public registration. Create users with `createsuperuser` or from the
in-app Users page (admins only).

## Documentation

| Guide | |
| --- | --- |
| [Architecture](docs/ARCHITECTURE.md) | Stack, apps, data flow |
| [Deployment](docs/DEPLOYMENT.md) | Docker production stack, migrations, rollback |
| [Testing](docs/TESTING.md) | Backend + frontend + CI |
| [AI commands](docs/AI_COMMANDS.md) | Tiers, confirmation, undo, safety model |
| [Backup & recovery](docs/BACKUP.md) | pg_dump / restore |

## Quick start (local development)

### Backend

```bash
cd Backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt  # runtime deps are in requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Admin at `http://localhost:8000/admin/`. Leave `POSTGRES_DB` empty for SQLite;
set `POSTGRES_DB=crm` (and the other `POSTGRES_*`) for PostgreSQL. For local
PostgreSQL you can run `docker compose up -d postgres`.

### Frontend

```bash
cd Frontend
npm install
cp .env.example .env
npm run dev
```

Open `http://localhost:5173` and log in with your Django user.

## Production (Docker)

```bash
cp .env.example .env     # set POSTGRES_PASSWORD, DJANGO_SECRET_KEY, hosts, ANTHROPIC_API_KEY
docker compose build
docker compose up -d
docker compose exec backend python manage.py createsuperuser
curl -f http://localhost:8080/api/health/
```

Only the frontend (`:8080`) is published; it proxies `/api` to the backend. See
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the full guide.

## Roles

- **Admin** — full access: manage users, commission, pipelines/stages, all
  records; run AI commands.
- **Sales** — read shared data; create/manage their own companies, projects,
  tasks, activities, deals, and meetings; deal amounts owned by others are
  masked. No user/commission/pipeline administration; no AI commands.

## Testing

```bash
cd Backend  && python manage.py test          # backend
cd Frontend && npm run test && npm run build   # frontend
```
