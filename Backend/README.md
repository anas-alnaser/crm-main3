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

SQLite by default (leave `POSTGRES_DB` empty). For PostgreSQL set the
`POSTGRES_*` variables. All settings are environment-driven — see `.env.example`
for the full, documented list (JWT lifetimes, throttling, AI, security).

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

List responses are paginated: `{count,next,previous,page,page_size,total_pages,results}`.

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
