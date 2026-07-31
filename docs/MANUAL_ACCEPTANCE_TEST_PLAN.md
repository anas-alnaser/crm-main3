# Manual Acceptance Test Plan

A step-by-step script for a tester (the "friend") to verify the workforce, leads,
audit, and multi-brand features end-to-end. Each scenario lists **steps** and the
**expected result**. Times are **Asia/Amman** (UTC+3).

> This build is **for acceptance testing**, not yet production. If any scenario
> fails, note the scenario number and what you saw.

---

## 0. Setup

### Start the app

Local dev:

```bash
# Terminal 1 — backend
cd Backend
python -m venv .venv && . .venv/Scripts/activate      # (Windows Git Bash)
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_acceptance_data                  # creates tagged test data
python manage.py runserver

# Terminal 2 — frontend
cd Frontend
npm install
cp .env.example .env
npm run dev
```

Open `http://localhost:5173`.

### Test accounts (from `seed_acceptance_data`)

| Role | Username | Password |
| --- | --- | --- |
| Admin | `acc_admin` | `acceptance-pass-123` |
| Employee (shift-required) | `acc_rep` | `acceptance-pass-123` |

The employee already has a Sun–Thu, 9 AM–9 PM policy (target 3h/day, JOD 150) and
3 tagged test leads. **No real phone numbers are used.**

### Simulating time-based rules

Shift start/end depends on the **real Jordan clock**. To test "too early" /
"too late" without waiting, temporarily change the employee's policy window on
the **Workforce → (or Django admin) → Employee work policy** (e.g. set the window
to the current hour ±1) — or use the Django admin at `/admin/`. Remember to
restore Sun–Thu 09:00–21:00 afterwards.

### Cleanup (after testing)

```bash
cd Backend
python manage.py seed_acceptance_data --cleanup   # removes ONLY tagged data
```

---

## A. Shifts & presence

**1. Admin login.** Log in as `acc_admin`. → Lands on the workspace; admin nav
shows Workforce, Audit Log, Brand Profiles, Users, Settings.

**2. Employee creation.** Users → create a user (role Sales, temp password ≥ 8).
→ Appears in the list; can log in.

**3. Work policy assignment.** As admin, open Django admin `/admin/workforce/` (or
the API) and confirm `acc_rep` has an active shift-required policy Sun–Thu,
09:00–21:00, 180 min/day. → Policy present and active.

**4. Shift before 9:00 AM.** Set the policy window start to a time later than now
(simulating "before open"), log in as `acc_rep`, go to **My Shift**, click
**Start Shift**. → Rejected with "window opens at HH:MM"; Start stays disabled;
an amber off-shift banner is shown.

**5. Shift at a valid time.** Restore the window to include now (e.g.
09:00–21:00 during the day). On **My Shift**, click **Start Shift**. → Status
becomes **On shift**; a current-session timer appears; the off-shift banner
disappears.

**6. Multiple shifts in one day.** End the shift (scenario 7), then Start again.
→ A second session starts; "Sessions today" increments; credited-today keeps the
earlier time.

**7. Manual End Shift.** Click **End Shift**. → A confirmation dialog greets you
by the employee's real name and shows the duration from the server
("Hi Acceptance Rep, you have worked for … today."). Confirm. → Back to
**Off shift**; you remain **logged in**.

**8. Confirmation duration.** Verify the duration in scenario 7 matches roughly
the time since you started (server-computed, not zero). → Reasonable value.

**9. Ten-minute inactivity.** Start a shift. Leave the browser completely idle
(no typing/clicking) for just over 10 minutes (or run
`python manage.py close_stale_work_sessions` after 10 min to simulate the
scheduler). → The session auto-closes; **My Shift** shows a clear
"closed automatically" notice; the full 10 idle minutes are credited.

**10. Staying logged in after inactivity.** After scenario 9, refresh. → You are
still logged in, just **off shift**.

**11. Off-shift mutation blocking.** While off shift as `acc_rep`, go to Companies
and try to create/edit a company. → Blocked; a toast/permission message explains
you are off shift (server returns 403 `off_shift`). Reading pages still works.

**12. Starting another session.** Start a shift again within the window. → Allowed;
new session; totals accumulate.

**13. 9:00 PM boundary.** Set the window end to a minute from now (simulating
approaching 9 PM) with an active session, wait past it (or run the stale-session
command). → The session closes with reason "working window ended"; time after the
boundary is **not** credited. Trying to Start after the end time is rejected
("too late"). Restore the window afterwards.

**14. Overtime.** Accumulate more than 3 hours in a day (adjust the target down
temporarily if you don't want to wait). → Credited exceeds target; **Overtime**
shows a positive value; you are **not** blocked at 3 hours.

---

## B. Audit

**15. Audit records.** As admin, open **Audit Log**. → You see events for the
actions above: login success, shift started/ended/closed-by-inactivity/closed at
9 PM, company create attempts, etc. Expand an event → safe metadata and old/new
values; **no passwords, tokens, or keystrokes** anywhere.

**31. Audit filtering.** Filter by employee = `acc_rep`, category = `shift`, and a
date range; search a keyword. → List narrows correctly; pagination works; **Export
CSV** downloads a file.

---

## C. Leads

**16. Excel upload.** As admin, go to **Leads**. Prepare a small `.xlsx` with a
**Name** and **Phone** header and a few rows (use fake numbers like
`0790000010`). Choose `acc_rep` as assignee and upload. → Import succeeds; a toast
reports imported/duplicate counts; leads appear assigned to the rep.

**17. Invalid Excel.** Upload a `.txt` file, then an `.xlsx` missing the Name/Phone
headers. → Rejected with a clear message (bad extension / missing headers);
nothing is imported.

**18. Duplicate leads.** Upload a file containing a phone that already exists (and
a row duplicated within the file). → Those rows are counted as duplicates and
**not** re-created.

**19. Lead assignment.** As admin, open a lead and reassign it to another user.
→ Assignment changes; an audit event is recorded.

**20. No answer.** Log in as `acc_rep`, start a shift, open a lead, log a contact
attempt with outcome "no answer" and status **No answer**. → Attempt saved; status
updates; history shows the attempt.

**21. Follow-up.** Log a contact attempt setting status **Follow up** *without* a
date. → Rejected ("follow-up date required"). Add a date/time and retry. → Saved;
the lead shows a follow-up time.

**22. Interested.** Set a lead to **Interested**. → Status updates; conversion
becomes available.

**23. Not interested.** Set a lead to **Not interested**. → Terminal outcome.

**24. Red visual status.** Look at the Leads list and the not-interested lead's
drawer. → The row/name renders in **red**; the drawer explains it is terminal.

**25. Admin reopen.** As `acc_admin`, open the not-interested lead and click
**Reopen with reason**; enter a reason. → Lead returns to **New**; the reason is
stored and audited. (Trying to reopen without a reason is refused.)

**26. CRM conversion.** As `acc_rep` (on shift), open an interested lead → **Convert
to client**. → A CRM client is created and linked; the lead becomes **Converted**;
lead + contact history is preserved.

**27. Existing-client conversion.** Convert a lead whose name/phone matches an
existing company (use **match candidates**), linking to that client instead of
creating a new one. → Lead links to the existing client; no duplicate created.

**28. Deal creation.** Convert a lead with "create deal" and a value. → A deal is
created in the default pipeline, owned by the rep, linked to the client and lead.
Converting the same lead again is refused ("already converted").

**Off-shift lead work.** End the shift and try to log a contact attempt or convert.
→ Blocked (`off_shift`).

---

## D. Workforce dashboard

**29. Workforce dashboard.** As admin, open **Workforce**, select `acc_rep`,
period **Current month**. → Work metrics (credited, expected, overtime, sessions,
days worked), lead metrics (assigned/contacted/converted/conversion rate), CRM
metrics, a salary panel (informational, no auto-deduction), and a daily breakdown
table all render.

**30. Inactivity-count reporting.** In the dashboard, find the inactivity-closure
count and the observation line ("… had N inactivity closures during this
period."). → Matches the closures you triggered in scenario 9.

---

## E. Multi-brand documents

**32. Fuel brand.** As admin, open **Brand Profiles**. → Fuel Dezign, Morph Studio,
Morph Solutions are listed. Issue an **Invoice** with brand **Fuel Dezign**.
→ Document number starts `FUEL-INV-<year>-…`.

**33. Morph Studio brand.** Issue an invoice with **Morph Studio**. → Number starts
`MORPH-STUDIO-INV-…`.

**34. Morph Solutions brand.** Issue a **Contract** with **Morph Solutions**.
→ Number starts `MORPH-SOLUTIONS-CON-…`.

**35. Shared Morph legal details.** Confirm Morph Studio and Morph Solutions map to
the **same** legal profile (Django admin → Brand profiles → legal entity). → Both
point at the `morph` legal entity; Fuel points at its own.

**36. Historical document immutability.** After issuing a Fuel document, edit the
Fuel brand's accent color / display name and save. Re-open the earlier document's
snapshot (Django admin → Generated documents → snapshot). → The old document's
stored brand name/values are **unchanged**.

> Note: the visual PDF **template/layout** is not part of this build (see
> `docs/MULTIBRAND_DOCUMENTS.md`). Legal identifiers must be entered by an admin
> before real use — the tester should confirm the admin screens accept them, not
> that a finished branded PDF renders.

---

## F. Database & operations

**37. Supabase health.** (Optional, needs a Supabase dev project + local
`Backend/.env.supabase.local`.) Run `python manage.py check_supabase --health-check`.
→ Connects, prints a **redacted** target, server/database/timezone, schema/table
listing, and a passing read/write probe. **No credentials are printed.**

**38. Database verification.** After migrating Supabase (see
`docs/SUPABASE_CUTOVER_CHECKLIST.md`), `python manage.py showmigrations` shows all
applied and expected tables exist.

**39. Backup.** Follow `docs/BACKUP.md` / the cutover checklist to take a backup
(`pg_dump` or `dumpdata`). → A backup file is produced.

**40. Rollback.** Point `DATABASE_URL` back to the previous database and restart.
→ The app runs against the old database; nothing was deleted.

---

## Highest-risk scenarios to test first

1. **9 (inactivity)** + **13 (9 PM cap)** — the crediting maths and auto-close.
2. **11 (off-shift blocking)** — server-side enforcement, not just UI.
3. **26–28 (conversion)** — atomicity + duplicate prevention.
4. **36 (snapshot immutability)** — historical documents must never change.
5. **15/Audit privacy** — confirm no secrets/keystrokes are ever stored.

## Cleanup reminder

```bash
cd Backend && python manage.py seed_acceptance_data --cleanup
```
