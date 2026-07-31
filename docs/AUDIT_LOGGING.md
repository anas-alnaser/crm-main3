# Audit Logging & Privacy

The workspace keeps a clear, server-authoritative record of meaningful business
activity — **without becoming a keylogger**.

## Privacy stance (what is NEVER stored)

- Passwords or temporary passwords
- JWT access/refresh tokens, `Authorization` headers
- Database connection strings / secret keys
- Raw request bodies indiscriminately
- **Raw keystrokes, typed form text, mouse coordinates, movement paths,
  clipboard contents, or screenshots**

A recursive redaction utility (`audit/redaction.py`) strips any field whose name
looks sensitive (`password`, `token`, `secret`, `authorization`, `api_key`,
`jwt`, `database_url`, …) from every metadata / old-value / new-value payload
**before it is saved** — call sites are not trusted to do it themselves.

The employee-facing privacy notice is available at
`GET /api/audit-events/privacy-notice/`.

## Server-authoritative events (the source of truth)

Recorded with `audit.services.record_event(...)`:

- **Auth** — login success, login failure (attempted username only), logout.
- **Shift** — started, manually ended, closed by inactivity, closed at 9 PM,
  closed by administrator.
- **Policy** — work policy created/changed.
- **CRM** — record created / updated (old→new diff) / archived / restored;
  deal moved.
- **Leads** — imported, assigned, viewed, contact attempt, status changed,
  reopened, converted.
- **Documents** — generated, issuing brand selected.
- **Users** — created, deactivated, reactivated.
- **AI** — command submitted, executed, blocked, confirmed, undone.
- **Security** — audit exported, permission denials.

Each event stores: user, related work session (when relevant), timestamp, action
code, category, entity type + id, a human-readable summary, request id, safe
metadata, redacted old/new values, IP address, and a user-agent **description**.

## Frontend telemetry (supplemental only)

A **controlled whitelist** of UI events may be reported by the browser
(`POST /api/telemetry/`): `page.opened`, `nav.selected`, `button.selected`,
`dialog.opened`, `lead.opened`, `contact.initiated`, `export.requested`,
`pdf.opened`, `brand.selected`, `filter.applied`. Anything else is **rejected**.
Telemetry is de-duplicated over a short window and stored with `source=client`.
Database-changing server events remain authoritative — telemetry never is.

## Admin audit viewer

`/audit` (admin only), backed by `GET /api/audit-events/`:

- Filters: employee, category, action, entity type, work session, source, date
  range (`from`/`to`), and free-text search.
- Pagination, expandable safe metadata, old/new-value comparison.
- Read-only (no create/update/delete). Django admin exposes it read-only too.
- Safe CSV export (`/api/audit-events/export/`, capped, itself audited).
