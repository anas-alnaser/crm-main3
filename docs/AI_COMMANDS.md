# AI command safety model

Admin-only natural-language commands interpreted by the Anthropic API and
mapped onto a fixed set of intents. Three tiers:

## Tier 1 — auto (execute immediately when confident and fully resolved)

`create_meeting, create_task, log_activity, move_deal, create_deal,
create_company, add_note, schedule_followup`

Blocked from executing when confidence < threshold (default 0.75), a required
field is missing, or a referenced record is ambiguous — the response then
carries `needs_review` / `requires_disambiguation` with options, and nothing is
written.

## Tier 2 — confirmation required

`update_deal_value, update_deal_close_date, reassign_deal_owner,
edit_company_details, edit_meeting, update_task`

1. First request interprets, resolves records, validates, and returns a
   server-generated **preview** (old → new) plus a `confirmation_id`. **No
   database write happens.**
2. The server stores the validated draft in a single-use
   `AICommandConfirmation` bound to the requesting user, with a short TTL
   (default 5 min).
3. `POST /api/ai/command/confirm/ {confirmation_id}` re-runs the **stored**
   draft inside a transaction. A modified browser payload cannot change what
   executes — only the confirmation id is accepted.

Confirmations are rejected when: not found (404), owned by another user (403),
already used (409), cancelled (409), or expired (410). Cancel explicitly with
`POST /api/ai/command/cancel/`.

## Tier 3 — blocked

`delete_*, change_commission_rate, change_user_role, create_user,
deactivate_user, bulk_operation` — never mutate, always audited, and return a
readable refusal that the UI surfaces.

## Undo

Executed create/update actions return `undoable: true` and an `action_id`.
`POST /api/ai/command/undo/` reverses them atomically (delete for creates,
restore previous values for updates). Undo is owner-bound and single-use.

## Logging, errors, limits

- Every command and confirmation is logged to `AICommandLog` (visible in Django
  admin) with tier and outcome.
- Provider/interpretation errors are logged server-side and returned as a
  generic `provider_error` — internal details are never sent to the client.
- AI endpoints are admin-only, throttled (`THROTTLE_AI`, default 30/min), and
  limited to `AI_COMMAND_MAX_LENGTH` characters.

## Configuration

Set `ANTHROPIC_API_KEY`. Without it (or with `AI_COMMANDS_ENABLED=False`) the
endpoints return 503 and the UI shows a clear "not configured" message.
