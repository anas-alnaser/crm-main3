# Lead Workflow

Excel upload → assignment → contact → follow-up → CRM conversion. Enforced in
Django (server-side), scoped by role, and gated by shift status for sales users.

## Import (admins only)

`POST /api/lead-imports/upload/` (multipart). Required logical columns: **Name**
and **Phone**. Documented header aliases are accepted (e.g. "Full Name",
"Mobile", "WhatsApp", Arabic "الاسم"/"رقم الهاتف") — but nothing is guessed
silently; a workbook without a recognizable Name and Phone header is rejected
(`missing_headers`).

Validation (per row and per file):

- Extension `.xlsx`, content-type, size (`LEAD_IMPORT_MAX_BYTES`, default 5 MB),
  max rows (`LEAD_IMPORT_MAX_ROWS`, default 5000).
- Empty rows are skipped; missing name / invalid phone → **invalid**.
- **Formula cells** (values starting with `=`) are rejected.
- Malformed workbooks → `bad_workbook`.

Add `preview=true` to validate and return counts **without persisting** anything.
Otherwise a `LeadImportBatch` is created, leads are bulk-created and (optionally)
assigned to one employee. Response counts: imported, invalid, duplicate, skipped,
assigned.

### Phone normalization & de-duplication

Each lead stores the original phone, a normalized phone (`+962…` E.164-style),
and a country context. Jordanian formats (`0790…`, `+962…`, `00962…`, spaced /
dashed) all normalize to the same value so duplicates collide. De-duplication
runs **within the workbook**, **within the batch**, and **against existing
leads**. Duplicates are reported, never silently created.

## Roles

| Capability | Admin | Sales |
| --- | --- | --- |
| Upload spreadsheets | ✅ | ❌ |
| View leads | all | only assigned |
| Assign / reassign | ✅ | ❌ |
| Add contact attempts / notes | ✅ | ✅ (on shift) |
| Update allowed statuses | ✅ | ✅ (on shift) |
| Schedule follow-up | ✅ | ✅ (on shift) |
| Convert eligible leads | ✅ | ✅ (on shift) |
| Delete leads | ❌ (disabled) | ❌ |
| Reopen terminal leads | ✅ (reason required) | ❌ |

A sales user requesting another user's lead by id gets **404** (queryset-scoped).

## Statuses

`new → contacted → no_answer → follow_up → interested → not_interested → converted`

- **new** — assigned, not yet contacted.
- **contacted** — a contact attempt was made without a more specific outcome.
- **no_answer** — preserved; more attempts and follow-ups allowed. Conversion is
  allowed **only** when the employee deliberately converts **and provides a
  reason**.
- **follow_up** — requires a follow-up date/time; overdue follow-ups are
  surfaced (`?overdue=true`).
- **interested** — conversion allowed.
- **not_interested** — **terminal**, shown prominently in **red**, never deleted
  automatically, normal conversion blocked. An **admin** may reopen it with a
  **required, audited reason**.
- **converted** — preserved and linked to the created/linked CRM client (and
  optional deal); records who converted it and when. Duplicate conversion is
  prevented.

## Contact attempts

Each attempt (`POST /api/leads/{id}/contact/`) is stored separately with lead,
employee, active work session, timestamp, method (call/whatsapp/sms/email/other),
outcome, notes, optional follow-up date, and the resulting status. Sales users
can only set the sales-settable statuses; setting `follow_up` requires a date.

## Conversion

`POST /api/leads/{id}/convert/` is **atomic, transactional, idempotent,
permission-checked, shift-checked, and duplicate-aware**:

1. Reconcile the active shift (write is blocked off shift).
2. Confirm the employee may access the lead.
3. Confirm the lead is convertible (not already converted; not `not_interested`;
   `no_answer` needs a reason).
4. Search existing CRM clients (`GET /api/leads/{id}/match-candidates/`).
5. Link to a chosen existing client, or create a new one.
6. Optionally create a deal (default pipeline's first stage, owned by the
   converter).
7. Link the lead to the client/deal; preserve all lead + contact history.
8. Record audit events; the frontend refreshes related queries.

The lead row is locked (`select_for_update`) so a concurrent second attempt
cannot create a duplicate client/deal — it gets `already_converted`.

## Metrics

Per-employee lead metrics feed the workforce dashboard: assigned, viewed,
contacted, attempts, no-answer, follow-ups scheduled, overdue follow-ups,
interested, not-interested, converted, conversion rate, clients created, deals
created/won from leads.
