# Backup & recovery

The only stateful component is PostgreSQL (Docker volume `postgres_data`).

## Backup

```bash
# Logical dump (recommended)
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-crm}" "${POSTGRES_DB:-crm}" > backup_$(date +%F).sql

# Compressed custom-format dump
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-crm}" -Fc "${POSTGRES_DB:-crm}" > backup_$(date +%F).dump
```

Schedule the above with cron/systemd timers and copy the artifact off-host.

## Restore

```bash
# Into a running, empty database
cat backup_YYYY-MM-DD.sql | docker compose exec -T postgres psql -U "${POSTGRES_USER:-crm}" "${POSTGRES_DB:-crm}"

# From a custom-format dump
docker compose exec -T postgres pg_restore -U "${POSTGRES_USER:-crm}" -d "${POSTGRES_DB:-crm}" --clean < backup_YYYY-MM-DD.dump
```

## Volume snapshot (alternative)

```bash
docker run --rm -v fueldezign-crm_postgres_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/pgdata_$(date +%F).tgz -C /data .
```

## Recovery drill

1. Stand up a throwaway stack, restore the latest backup, run
   `docker compose exec backend python manage.py migrate --plan` (should show no
   pending migrations), and verify `GET /api/health/` plus a login.
2. Keep at least 7 daily backups; test a restore monthly.
