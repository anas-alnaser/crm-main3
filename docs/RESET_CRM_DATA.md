# Full CRM reset

The full reset **permanently deletes all CRM business data and every other
application user**, preserving only the currently authenticated superadmin and
the required system/configuration data. It is irreversible.

> **The full reset permanently deletes CRM business data. It cannot be recovered
> unless a database backup exists.** Because Django writes straight to Supabase
> PostgreSQL, deleting rows here removes them from the production database.
> **Take a Supabase backup first** (`docs/BACKUP.md`).

There is one authoritative implementation, `Backend/crm/data_reset.py`, used by
both the API and the management command — the logic is never duplicated.

---

## What it deletes

All application/business data, including where present: every user except the
preserved superadmin, leads, lead contact attempts, lead import batches,
companies, deals, pipelines & stages, projects, tasks, activities, meetings, work
sessions, work policies & exceptions, audit events, AI‑command logs &
confirmations, generated documents & their snapshots, document sequences,
signatories, uploaded media (`StoredFile`), sales settings, and Django admin log
entries.

## What it preserves

- **The currently authenticated superadmin** — same id, username, email, password
  hash, and `active/staff/superuser/admin` flags. The password still
  authenticates afterwards.
- **The database schema** — tables, constraints, indexes.
- **Django system data** — `django_migrations`, `django_content_type`,
  `auth_permission`, required groups, and applied migrations.
- **The required brand/legal structure** — Fuel Dezign, the shared Morph legal
  profile, Morph Studio, Morph Solutions — reseeded idempotently from the
  authoritative `branding` migration (no legal identifiers are fabricated).

## Safety properties

- One `transaction.atomic()` — any failure rolls the entire reset back.
- The preserved user is locked with `select_for_update` and revalidated before
  and after; it is excluded from every delete and protected from cascades.
- FK‑aware deletion order (children before parents). No constraint is disabled,
  `TRUNCATE CASCADE` is never used, and the schema/migrations are never touched.
- PostgreSQL identity sequences for the cleared business tables are reset.
- A PostgreSQL advisory lock (cache fallback off‑Postgres) prevents two resets
  from running at once (returns HTTP 409 / a conflict error).

---

## A. Reset from the UI (Settings → Danger Zone)

Visible only to a superadmin.

1. Sign in as the superadmin: <https://morph-fuel-crm.anasalnaser24.workers.dev>
2. Open **Settings → Danger Zone**.
3. Click **Preview full reset**. Review the preserved account, the number of
   other users to delete, the per‑model counts, the total rows, the config to be
   preserved/reseeded, and the preview expiry.
4. Enter your **current password**.
5. Type exactly: `DELETE ALL CRM DATA`.
6. Tick **"I understand that this permanently deletes CRM data and cannot be
   undone."**
7. Click **Permanently reset CRM**.
8. On success the app clears cached data, keeps you logged in, refetches your
   account, navigates to the dashboard, and shows *"CRM data reset completed.
   Your account was preserved."*
9. Verify the business pages (Leads, Companies, Deals, …) are empty and that you
   are still logged in.

The **preview issues a short‑lived, signed, single‑use token** (≈10 minutes)
bound to your user id and the previewed data snapshot. Execute requires that
token; it expires, is consumed on use, and is invalidated once the data changes
(e.g. after a completed reset). The password is never stored, logged, or placed
in a URL.

---

## B. Reset from the API

```
GET  /api/admin/data-reset/preview/     # superadmin only; no writes; returns counts + preview_token
POST /api/admin/data-reset/execute/     # superadmin only
```

Execute body:

```json
{
  "current_password": "…",
  "confirmation": "DELETE ALL CRM DATA",
  "preserved_user_id": 1,
  "preview_token": "<from preview>"
}
```

`preserved_user_id` must equal your own user id. The endpoints are rate‑limited.

---

## C. Reset from the command line

The command reuses the same service. It prints **model names and safe counts
only** — never secrets, connection strings, or field values.

### Dry run (no changes)

```bash
cd Backend
python manage.py reset_crm_data --keep-user-email <SUPERADMIN_EMAIL> --dry-run
```

or by id: `--keep-user-id <ID>`. Exactly one of `--keep-user-id` /
`--keep-user-email` is required, and the selected user must be an active
superadmin (staff + superuser + `role=admin`).

### Real reset (irreversible)

```bash
cd Backend
python manage.py reset_crm_data --keep-user-email <SUPERADMIN_EMAIL> --confirm "DELETE ALL CRM DATA"
```

- A real reset refuses to run on a non‑PostgreSQL database unless
  `--allow-non-postgres` is given (controlled tests only).
- To target an alternative environment (e.g. Supabase) either export
  `DJANGO_ENV_FILE` before running, or pass `--env-file <file>` (loaded relative
  to `Backend/`). **Do not hardcode the owner's email or password.**

> The real Supabase env file (`Backend/.env.supabase.local`) is git‑ignored and
> must never be committed or printed.

---

## Post‑reset checks

1. You are still logged in as the same superadmin (same id/username).
2. Your password still authenticates.
3. Business pages (Leads, Companies, Deals, Projects, Tasks, Activities,
   Meetings) are empty.
4. The Users page lists only your account.
5. Brand Profiles still shows Fuel Dezign, Morph Studio, Morph Solutions.
6. `GET /api/health/` returns `200` with `database: true`.

## Recovery / rollback

- **Before** a completed transaction: any error rolls the whole reset back
  automatically — nothing is deleted.
- **After** a completed reset: the only recovery is to **restore a Supabase
  database backup** taken beforehand (`docs/BACKUP.md`). There is no in‑app undo.
