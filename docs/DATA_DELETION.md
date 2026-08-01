# Data deletion & the full CRM reset

This CRM distinguishes several very different operations. Most are reversible or
non‑destructive; two are irreversible and restricted to a **superadmin**.

> **Deleting a record through the Django backend permanently removes the
> corresponding row from the Supabase PostgreSQL database, because Supabase is
> the CRM's production database.** There is no separate copy — once a row is
> deleted it is gone unless a database backup exists (see `docs/BACKUP.md`).

---

## 1. The operations at a glance

| Operation | What it does | Who can do it | Reversible? |
|-----------|--------------|---------------|-------------|
| **Delete** (normal) | Standard delete for ordinary records (activities, tasks, meetings, projects, deals) subject to owner/admin + on‑shift rules | Admin, or the record's creator where ownership allows | Row is gone; not reversible |
| **Archive / Restore** | Hides a **company** from active lists while preserving its deals & projects | Admin | Yes — Restore |
| **Deactivate / Reactivate** | Disables a **user** while preserving ownership & history | Admin | Yes — Reactivate |
| **Permanent delete** | Irreversibly deletes one lead, company, or user | **Superadmin only** | **No** |
| **Full CRM reset** | Irreversibly deletes *all* business data + all other users, preserving only the current superadmin | **Superadmin only** | **No** |

### What is a "superadmin"?

A superadmin is stricter than a normal `role="admin"` user. All five must hold
(`accounts.permissions.is_super_admin`):

- `is_authenticated`
- `is_active`
- `is_staff`
- `is_superuser` (Django superuser)
- `role == "admin"`

A normal `role="admin"` staff user is **not** a superadmin and cannot use any
permanent‑delete or full‑reset endpoint. Every such endpoint enforces this on
the **server** — hiding a button in the UI is never the security boundary.

---

## 2. Normal protections (unchanged)

These deliberate blocks remain in place for regular users:

- **Leads** — the standard `DELETE /api/leads/{id}/` returns **405**; leads are
  never deleted through the normal workflow.
- **Companies** — `DELETE /api/clients/{id}/` returns **405**; use Archive /
  Restore.
- **Users** — `DELETE /api/users/{id}/` returns **405**; use Deactivate /
  Reactivate.
- **On‑shift rule** — shift‑required employees must be on shift to make business
  writes. Off‑shift attempts return a clear `off_shift` error, now surfaced in
  the UI instead of a generic message.

The superadmin capabilities below are **added alongside** these, as separate,
explicit, re‑authenticated actions — they do not weaken the normal rules.

---

## 3. Individual lead permanent delete

Endpoints (superadmin only, rate‑limited):

```
GET  /api/leads/{id}/delete-impact/      # read‑only summary, no writes
POST /api/leads/{id}/permanent-delete/   # irreversible
```

Execution body:

```json
{ "current_password": "…", "confirmation": "DELETE LEAD", "lead_id": 123 }
```

The server validates, in order: superadmin → current password → exact phrase
`DELETE LEAD` → `lead_id` matches the URL → the lead still exists → the lead is
**not converted**. It then locks the row (`select_for_update`), re‑checks
conversion state under the lock, deletes the lead's `LeadContactAttempt` rows and
the lead, and records a safe audit event (`lead.permanently_deleted`) containing
only the lead id, actor id, and the count of deleted attempts — never the phone,
notes, or attempt content.

**It never deletes** the import batch, a converted client/deal, the assigned or
creating user, work sessions, or any unrelated lead.

### Why converted leads are protected

A converted lead is linked to real business records (a client and possibly a
deal). Deleting it would orphan or endanger that history, so permanent deletion
of a converted lead is **blocked by default** and the UI shows:

> Converted leads cannot be permanently deleted because they are linked to
> business records.

The linked client/deal are always preserved.

---

## 4. Company permanent delete

Endpoints (superadmin only):

```
GET  /api/clients/{id}/delete-impact/
POST /api/clients/{id}/permanent-delete/
```

Body:

```json
{ "current_password": "…", "confirmation": "DELETE COMPANY", "client_id": 123, "cascade_confirmed": true }
```

The impact endpoint reports the dependent counts before anything is deleted:

- **Deleted with the company** (FK `CASCADE`): its **deals** and **projects**.
- **Detached** (FK `SET_NULL`): tasks, activities, meetings, generated
  documents, and conversion‑linked leads (their `company`/link becomes null).

If any dependencies exist, `cascade_confirmed` must be `true` — a second explicit
confirmation so a large related history is never destroyed silently. The final
delete runs in a single transaction with the row locked. Archive / Restore remain
the normal, non‑destructive default.

---

## 5. User permanent delete

Endpoints (superadmin only):

```
GET  /api/users/{id}/delete-impact/
POST /api/users/{id}/permanent-delete/
```

Body:

```json
{ "current_password": "…", "confirmation": "DELETE USER", "user_id": 123 }
```

Rules:

- **You cannot delete yourself** — `request.user` is always protected.
- Ownership references are inspected first:
  - **`SET_NULL`** fields (created leads/clients/projects/tasks/activities,
    assignments, audit authorship, etc.) are simply cleared — history is
    anonymised, not destroyed.
  - **`PROTECT`** references block the delete: if the user owns **deals**,
    **meetings**, or **AI‑command logs**, those must be reassigned first. The API
    returns a clear `protected_dependencies` error instead of failing at the
    database — a `ProtectedError` can never occur.
  - **`CASCADE`** dependents (the user's work policy and work sessions) are
    removed with the user.
- The CRM is never left with no admin‑level user.

Both the actor and target rows are locked, the actor's superadmin status is
re‑validated under the lock, and the delete runs in one transaction. Deactivate /
Reactivate remain the normal default.

### Why users cannot delete themselves

A superadmin deleting their own account could lock everyone out and would remove
the very identity the destructive operations are authorised against. The self
account is always preserved; use Deactivate for another admin instead if needed.

---

## 6. Full CRM reset

See **`docs/RESET_CRM_DATA.md`** for the complete procedure (UI, API, management
command, dry‑run, and post‑reset checks).

In short, a superadmin can permanently delete **all** CRM business data and
**every other user**, preserving only their own account and the required
Fuel/Morph brand & legal structure.

> **The full reset permanently deletes CRM business data. It cannot be recovered
> unless a database backup exists.**

---

## 7. Protected / system data (never individually deletable)

The deletion features deliberately do **not** add normal per‑record deletion for:

- **Audit events** — the tamper‑resistant record of what happened.
- **Required brand / legal configuration** — Fuel Dezign, the shared Morph legal
  profile, Morph Studio, Morph Solutions.
- **Django system tables** — `django_migrations`, `django_content_type`,
  `auth_permission`, applied migrations, required groups.
- **Document sequences** — deleting them mid‑year would corrupt invoice/receipt
  numbering (they are only reset as part of a full reset).

### Why Django system tables remain

`django_migrations`, content types, and permissions describe the **schema and
framework**, not your business data. Removing them would break the application
and the migration history. A reset clears *rows of business data*; it never
touches the schema, constraints, indexes, or migration records — and it never
uses `TRUNCATE CASCADE`, never disables constraints, and never drops tables.

---

## 8. Error messages

Destructive endpoints return safe, specific reasons the UI shows verbatim, e.g.:

- `You are off shift. Start your shift to make changes.`
- `You do not own this record.`
- `Converted leads cannot be permanently deleted…`
- `Incorrect password.`
- `The confirmation phrase must be typed exactly…`
- `Only a superadmin can perform this action.`

Stack traces, SQL, secrets, and internal exception detail are never exposed.

---

## 9. Backups

Because deletion is permanent at the database level, **take a Supabase backup
before any permanent delete or full reset.** See `docs/BACKUP.md`. Recovery after
a reset is only possible by restoring such a backup.
