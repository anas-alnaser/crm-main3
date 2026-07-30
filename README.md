# Fueldezign CRM

Private CRM for running Fueldezign, a branding/design/dev agency.

## Architecture

- `Backend`: Django REST Framework API, Django admin, JWT login, business data, SQLite local fallback, PostgreSQL-ready settings.
- `Frontend`: React/Vite dashboard for managing clients, projects, tasks, and activities.

There is no public registration flow. Create users from Django admin with `createsuperuser` or the admin user interface.

## Local PostgreSQL

```bash
docker compose up -d
```

This starts PostgreSQL on `localhost:5432` with database/user/password `crm`.

## Backend

```bash
cd Backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open the admin at `http://localhost:8000/admin/`.

For SQLite local development, leave `POSTGRES_DB` empty in `Backend/.env`. For PostgreSQL, set `POSTGRES_DB=crm`.

## Frontend

```bash
cd Frontend
npm install
cp .env.example .env
npm run dev
```

Open `http://localhost:5173` and log in with your Django user.
