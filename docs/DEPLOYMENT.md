# Deployment guide

The production stack runs three containers: PostgreSQL, the Django API
(gunicorn), and the React SPA (nginx, which also proxies `/api` to the API).

## 1. Configure

```bash
cp .env.example .env
# Edit .env and set at minimum:
#   POSTGRES_PASSWORD  - strong password
#   DJANGO_SECRET_KEY  - long random 50+ char value
#   DJANGO_ALLOWED_HOSTS, CORS_ALLOWED_ORIGINS, CSRF_TRUSTED_ORIGINS - your host
#   ANTHROPIC_API_KEY  - only if using AI commands (else AI_COMMANDS_ENABLED=False)
```

Generate a secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

For real TLS deployments leave `SECURE_SSL_REDIRECT=True` (default) and terminate
TLS at a reverse proxy that sets `X-Forwarded-Proto`. For a plain-HTTP trial set
`SECURE_SSL_REDIRECT=False`.

## 2. Build and start

```bash
docker compose config      # validate the compose file
docker compose build       # build backend + frontend images
docker compose up -d        # start postgres, backend, frontend
```

Migrations and `collectstatic` run automatically on backend start
(`Backend/entrypoint.sh`).

## 3. Create the first admin

```bash
docker compose exec backend python manage.py createsuperuser
```

Then create additional users from the CRM (Users page) or Django admin.

## 4. Verify

```bash
curl -f http://localhost:8080/api/health/     # {"status":"ok","database":true}
# Open http://localhost:8080 and log in.
```

Health: `GET /api/health/` (unauthenticated) returns `status` and `database`.
The backend and postgres containers also have Docker `HEALTHCHECK`s
(`docker compose ps` shows health).

## 5. Migrations on later releases

```bash
docker compose build backend
docker compose up -d backend    # entrypoint re-runs migrate + collectstatic
# or explicitly:
docker compose exec backend python manage.py migrate
```

## 6. Shut down

```bash
docker compose down             # stop (keeps the postgres volume)
docker compose down -v          # stop and DELETE the database volume
```

## Rollback

- **Code**: redeploy the previous image tag / git revision and
  `docker compose up -d`.
- **Migrations**: `docker compose exec backend python manage.py migrate <app> <previous_migration>`.
  Review reversibility first; the only data migration (`sales.0004`) is a
  no-op-reversible backfill.
- Always take a database backup before a risky migration (see BACKUP.md).

## Backups & recovery

See [BACKUP.md](BACKUP.md).
