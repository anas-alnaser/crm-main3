# Workforce & Shift Policy

How employee work policies, shifts, presence, and time-crediting work. All time
decisions are made on the **server** (Django); the browser is never trusted.

## Timezone

The business timezone is **`Asia/Amman`** (`BUSINESS_TIMEZONE`, UTC+3). Timestamps
are stored in UTC; working-day boundaries and the 9:00 AM–9:00 PM window are
evaluated in the business timezone. Weekday convention follows Python's
`date.weekday()` (Monday=0 … Sunday=6).

## EmployeeWorkPolicy

One policy per user (`/api/work-policies/`, admin only). Key fields:

| Field | Default | Meaning |
| --- | --- | --- |
| `shift_tracking_required` | `true` | Whether shifts are enforced for this user |
| `is_active` | `true` | Inactive policies block starting shifts |
| `working_days` | Sun–Thu `[6,0,1,2,3]` | Allowed working weekdays |
| `earliest_start_time` | `09:00` | Window opens |
| `latest_end_time` | `21:00` | Hard close boundary |
| `daily_target_minutes` | `180` (3h) | Daily target |
| `monthly_target_minutes` | none | Optional monthly target (e.g. 3600 = 60h) |
| `basic_salary` / `salary_currency` | none / `JOD` | Informational only |
| `overtime_allowed` | `true` | Overtime is reported |

**Admins are not shift-tracked** unless an admin explicitly assigns them a
policy with `shift_tracking_required = true`. Users without a policy are never
blocked.

### Exceptions (`WorkPolicyException`)

Admin-approved, date-specific overrides:

- `extra_working_day` / `one_day_override` — allow a shift on a non-working day.
- `custom_window` — temporary start/end time for one date.
- `holiday` — a day off (blocks starting a shift that day).

## Shifts

- **Start** (`POST /api/workforce/shift/start/`) is allowed only when: the policy
  is active and shift-tracking is required, the local date is a working day (or
  an approved exception), the current Jordan time is **≥ 09:00 and < 21:00**, and
  no session is already active. Clear error codes: `too_early`, `too_late`,
  `disallowed_day`, `policy_inactive`, `already_active`, `not_configured`.
- **Multiple sessions per day** are allowed (e.g. 9:00–10:00, 14:00–15:00,
  19:30–20:30). All credited sessions contribute to the same daily total. The
  employee is **not** blocked after reaching the 3-hour target; extra time is
  reported as overtime.
- **Manual end** (`POST /api/workforce/shift/end/`) closes only the current
  session. A server-generated preview (`.../end/preview/`) shows the real
  duration and greets the employee by their actual display name. The employee
  stays logged in and may start another shift later within the window.

Only **one active session per employee** is possible, enforced by a partial
unique database constraint (`ended_at IS NULL`). Concurrent start attempts get a
clean `already_active` error, not a duplicate.

## Presence & the ten-minute inactivity rule

Genuine keyboard/mouse interaction (keydown, mousedown, pointerdown, touchstart,
wheel) marks the browser active. The frontend sends a **throttled heartbeat**
(~every 30s, only when interaction actually occurred, coordinated across tabs via
`BroadcastChannel`). **No keystrokes, typed text, coordinates, movement paths,
clipboard, or screenshots are ever recorded** — only "the user was active".

After **10 continuous minutes** without a valid heartbeat, the session
auto-closes:

```
automatic_end = last_activity_at + 10 minutes   (the full 10 idle minutes are credited)
```

…never exceeding the 9:00 PM boundary or an earlier closure. Example: last
interaction 2:00 PM, no further activity → session ends at 2:10 PM, crediting the
full ten minutes.

## The hard 9:00 PM boundary

9:00 PM Jordan time is an absolute cap:

- No session may start at or after 9:00 PM (`too_late`).
- An active session is closed no later than 9:00 PM (`working_window_ended`).
- Time after 9:00 PM is never credited.
- The employee stays logged in, off shift.

## Crediting

- All durations are computed on the server and stored as **integer seconds**
  (never floating-point hours).
- Credited seconds = `end − started`, where `end` is bounded by the inactivity
  deadline and the 9:00 PM cap.

## Server-side reliability (not just the browser)

Browser JavaScript alone is not trusted. Sessions are closed by:

1. **Request-time reconciliation** — every off-shift-guarded write reconciles the
   user's session first, so an expired shift blocks the write.
2. **A scheduled command** — `python manage.py close_stale_work_sessions`, run
   ~once per minute. It is idempotent, transaction-safe, and concurrency-safe.
   The Docker stack runs it in a lightweight `scheduler` service (no Redis/Celery).

### Scheduler setup options

- **Docker** — the `scheduler` service in `docker-compose.yml` loops the command
  every `SCHEDULER_INTERVAL` seconds (default 60).
- **cron** — `* * * * * cd /app/Backend && python manage.py close_stale_work_sessions --quiet`
- **systemd timer** — a `OnCalendar=*:0/1` timer running the same command.

## Off-shift enforcement

A shift-required employee may **read** the CRM while off shift but cannot make
business changes. Blocking is enforced server-side (`ShiftRequiredForWrite`) on
companies, projects, tasks, activities, meetings, deals, and all lead work —
returning `403` with code `off_shift`. A disabled button alone is never relied
upon. Admins (without a shift-required policy) are exempt.

## Employee dashboard

`/my-shift` shows on/off-shift state, local Jordan time, the allowed window,
Start/End buttons, current session elapsed, credited-today, target, remaining,
overtime, and a clear notice after any automatic inactivity closure.
