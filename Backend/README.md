# Fueldezign CRM Backend

Django REST API for the Fueldezign CRM. The API uses JWT login and Django admin for user creation. There is no public registration endpoint.

## Setup

```bash
cd Backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

By default, the backend uses SQLite for local development. To use PostgreSQL, set `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and `POSTGRES_PORT` in `.env`.

## API

- `POST /api/auth/login/` with `username` and `password`
- `POST /api/auth/refresh/` with `refresh`
- `GET /api/auth/me/`
- `/api/clients/`
- `/api/projects/`
- `/api/tasks/`
- `/api/activities/`

## Admin

Run `python manage.py createsuperuser`, then open `http://localhost:8000/admin/`.
