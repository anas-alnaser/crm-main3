"""Server-authoritative shift engine.

Everything time-related is decided here, never trusted from the browser:

* whether an employee may start a shift right now (working day + 9:00 AM–9:00 PM
  window in the business timezone, with admin-approved date exceptions),
* how much time a session has credited (whole integer seconds),
* when a session must auto-close (10-minute inactivity or the 9:00 PM cap),
* daily totals, target, remaining, and overtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from audit.models import AuditCategory
from audit.services import client_ip, record_event, user_agent

from .models import ClosingReason, EmployeeWorkPolicy, WorkSession
from .timezones import business_now, combine_local, local_date


class ShiftError(Exception):
    """A shift action was rejected. ``code`` is a stable machine-readable slug."""

    def __init__(self, code: str, message: str, extra: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra or {}


def inactivity_minutes() -> int:
    return int(getattr(settings, "WORKFORCE_INACTIVITY_MINUTES", 10))


# --- policy / lookup helpers ------------------------------------------------

def get_policy(user) -> EmployeeWorkPolicy | None:
    return EmployeeWorkPolicy.objects.filter(user=user).first()


def is_shift_required(user) -> bool:
    """True when this user must be on an active shift to make business changes."""
    policy = get_policy(user)
    return bool(policy and policy.is_active and policy.shift_tracking_required)


def active_session(user) -> WorkSession | None:
    return WorkSession.objects.filter(employee=user, ended_at__isnull=True).first()


@dataclass
class DayWindow:
    is_working_day: bool
    start_time: object  # datetime.time
    end_time: object
    reason: str = ""


def resolve_day_window(policy: EmployeeWorkPolicy, day) -> DayWindow:
    """Resolve the working window for ``day`` (a local date), applying any
    admin-approved exception for that date."""
    exception = policy.exceptions.filter(date=day).first()
    start_time = policy.earliest_start_time
    end_time = policy.latest_end_time
    is_working_day = policy.allows_weekday(day.weekday())

    if exception is not None:
        if exception.is_day_off:
            return DayWindow(False, start_time, end_time, reason="holiday")
        if exception.exception_type in {
            exception.ExceptionType.EXTRA_WORKING_DAY,
            exception.ExceptionType.ONE_DAY_OVERRIDE,
        }:
            is_working_day = True
        if exception.custom_start_time:
            start_time = exception.custom_start_time
        if exception.custom_end_time:
            end_time = exception.custom_end_time

    return DayWindow(is_working_day, start_time, end_time)


# --- crediting / closing maths ---------------------------------------------

def _window_end_dt(session: WorkSession) -> datetime:
    return combine_local(session.work_date, session.window_end_time, session.timezone)


def effective_close(session: WorkSession, now: datetime | None = None):
    """Return ``(end_dt, reason_or_None)`` for an active session.

    ``reason`` is set only when the session *should* be closed as of ``now``:
    inactivity (credit the full idle window up to ``last_activity + 10m``) or
    the hard 9:00 PM cap, whichever comes first. When neither has triggered,
    ``end_dt == now`` and ``reason`` is ``None``.
    """
    now = now or timezone.now()
    window_end = _window_end_dt(session)
    inactivity_deadline = session.last_activity_at + timedelta(minutes=inactivity_minutes())

    end = now
    reason = None
    if now >= inactivity_deadline:
        end = inactivity_deadline
        reason = ClosingReason.INACTIVITY
    # The 9:00 PM boundary is a hard cap that limits any later end.
    if end >= window_end:
        end = window_end
        reason = ClosingReason.WORKING_WINDOW_ENDED
    if end < session.started_at:
        end = session.started_at
    return end, reason


def credited_seconds_so_far(session: WorkSession, now: datetime | None = None) -> int:
    if not session.is_active:
        return session.credited_seconds
    end, _reason = effective_close(session, now)
    return max(0, int((end - session.started_at).total_seconds()))


# --- session lifecycle ------------------------------------------------------

def _close(session: WorkSession, *, end: datetime, reason: str, auto: bool, request=None, actor=None):
    session.ended_at = end
    session.closing_reason = reason
    session.credited_seconds = max(0, int((end - session.started_at).total_seconds()))
    session.auto_closed = auto
    session.save(update_fields=["ended_at", "closing_reason", "credited_seconds", "auto_closed", "updated_at"])
    record_event(
        action=f"shift.{reason}",
        category=AuditCategory.SHIFT,
        user=actor or session.employee,
        request=request,
        work_session=session,
        entity_type="WorkSession",
        entity_id=session.pk,
        summary=f"Work session closed ({session.get_closing_reason_display()}); credited {session.credited_minutes} min.",
        metadata={"auto_closed": auto, "credited_seconds": session.credited_seconds},
    )
    return session


def reconcile_session(session: WorkSession, now: datetime | None = None, request=None) -> WorkSession:
    """Close ``session`` if inactivity or the 9:00 PM cap has been reached.

    Idempotent: a already-closed session is returned untouched.
    """
    if not session.is_active:
        return session
    now = now or timezone.now()
    end, reason = effective_close(session, now)
    if reason is None:
        return session
    return _close(session, end=end, reason=reason, auto=True, request=request)


def reconcile_active_session(user, now: datetime | None = None, request=None) -> WorkSession | None:
    """Request-time reconciliation for a single user (row-locked, idempotent)."""
    now = now or timezone.now()
    with transaction.atomic():
        session = (
            WorkSession.objects.select_for_update()
            .filter(employee=user, ended_at__isnull=True)
            .first()
        )
        if session is None:
            return None
        return reconcile_session(session, now=now, request=request)


def start_shift(user, request=None, now: datetime | None = None) -> WorkSession:
    policy = get_policy(user)
    if policy is None:
        raise ShiftError("not_configured", "You do not have a work policy assigned. Ask an admin to set one up.")
    if not policy.is_active:
        raise ShiftError("policy_inactive", "Your work policy is currently inactive.")
    if not policy.shift_tracking_required:
        raise ShiftError("not_required", "Shift tracking is not required for your account.")

    # Close any session that should already have auto-closed before we evaluate.
    reconcile_active_session(user, now=now, request=request)

    now = now or timezone.now()
    local_now = business_now(policy.timezone)
    if now.tzinfo is not None:
        local_now = now.astimezone(local_now.tzinfo)
    today = local_now.date()
    window = resolve_day_window(policy, today)

    if not window.is_working_day:
        raise ShiftError(
            "disallowed_day",
            f"{today:%A} is not a working day for your policy." if window.reason != "holiday"
            else "An approved holiday is set for today.",
            extra={"working_days": policy.working_day_labels()},
        )

    now_time = local_now.time().replace(tzinfo=None)
    if now_time < window.start_time:
        raise ShiftError(
            "too_early",
            f"Your shift window opens at {window.start_time:%H:%M}. It is {now_time:%H:%M} now.",
            extra={"window_start": window.start_time.strftime("%H:%M"), "window_end": window.end_time.strftime("%H:%M")},
        )
    if now_time >= window.end_time:
        raise ShiftError(
            "too_late",
            f"Your shift window closed at {window.end_time:%H:%M}. It is {now_time:%H:%M} now.",
            extra={"window_start": window.start_time.strftime("%H:%M"), "window_end": window.end_time.strftime("%H:%M")},
        )

    try:
        with transaction.atomic():
            session = WorkSession.objects.create(
                employee=user,
                policy=policy,
                timezone=policy.timezone,
                daily_target_minutes=policy.daily_target_minutes,
                window_start_time=window.start_time,
                window_end_time=window.end_time,
                started_at=now,
                last_activity_at=now,
                work_date=today,
                start_ip=client_ip(request),
                start_user_agent=user_agent(request),
            )
    except IntegrityError:
        # Partial unique index tripped: a concurrent request already opened one.
        raise ShiftError("already_active", "You already have an active work session.")

    record_event(
        action="shift.started",
        category=AuditCategory.SHIFT,
        user=user,
        request=request,
        work_session=session,
        entity_type="WorkSession",
        entity_id=session.pk,
        summary=f"Shift started at {local_now:%H:%M} {policy.timezone}.",
        metadata={"work_date": str(today)},
    )
    return session


def end_shift(user, request=None, now: datetime | None = None) -> WorkSession:
    now = now or timezone.now()
    with transaction.atomic():
        session = (
            WorkSession.objects.select_for_update()
            .filter(employee=user, ended_at__isnull=True)
            .first()
        )
        if session is None:
            raise ShiftError("no_active_session", "You do not have an active work session to end.")
        # Manual end: close at now, but never credit past the 9:00 PM cap.
        window_end = _window_end_dt(session)
        end = min(now, window_end)
        reason = ClosingReason.WORKING_WINDOW_ENDED if now >= window_end else ClosingReason.MANUAL_END
        return _close(session, end=end, reason=reason, auto=(reason != ClosingReason.MANUAL_END), request=request, actor=user)


def admin_close_session(session: WorkSession, actor, request=None, now: datetime | None = None) -> WorkSession:
    now = now or timezone.now()
    if not session.is_active:
        return session
    window_end = _window_end_dt(session)
    end = min(now, window_end)
    with transaction.atomic():
        locked = WorkSession.objects.select_for_update().get(pk=session.pk)
        if not locked.is_active:
            return locked
        return _close(locked, end=end, reason=ClosingReason.ADMIN_CLOSED, auto=False, request=request, actor=actor)


def record_heartbeat(user, request=None, now: datetime | None = None):
    """Register genuine activity. Returns the (possibly auto-closed) session.

    No keystroke/mouse content is stored — only the fact that the user was
    active, as ``last_activity_at``.
    """
    now = now or timezone.now()
    with transaction.atomic():
        session = (
            WorkSession.objects.select_for_update()
            .filter(employee=user, ended_at__isnull=True)
            .first()
        )
        if session is None:
            return None
        # If it should already have closed, close it rather than extend it.
        _end, reason = effective_close(session, now)
        if reason is not None:
            return reconcile_session(session, now=now, request=request)
        session.last_activity_at = now
        session.save(update_fields=["last_activity_at", "updated_at"])
        return session


# --- reporting helpers ------------------------------------------------------

def sessions_for_day(user, day):
    return WorkSession.objects.filter(employee=user, work_date=day)


def day_totals(user, day, now: datetime | None = None) -> dict:
    now = now or timezone.now()
    sessions = list(sessions_for_day(user, day))
    total = 0
    active = None
    for session in sessions:
        if session.is_active:
            active = session
            total += credited_seconds_so_far(session, now)
        else:
            total += session.credited_seconds
    policy = get_policy(user)
    target_minutes = policy.daily_target_minutes if policy else getattr(settings, "WORKFORCE_DEFAULT_DAILY_TARGET_MINUTES", 180)
    target_seconds = target_minutes * 60
    return {
        "date": day,
        "credited_seconds": total,
        "target_seconds": target_seconds,
        "remaining_seconds": max(0, target_seconds - total),
        "overtime_seconds": max(0, total - target_seconds),
        "session_count": len(sessions),
        "active_session": active,
    }


def shift_status(user, now: datetime | None = None) -> dict:
    """The full off-shift/on-shift picture for the employee dashboard."""
    now = now or timezone.now()
    policy = get_policy(user)
    reconcile_active_session(user, now=now)
    session = active_session(user)
    local_now = business_now(policy.timezone if policy else None)
    today = local_date(now, policy.timezone if policy else None)

    if policy is None or not policy.is_active or not policy.shift_tracking_required:
        totals = day_totals(user, today, now)
        return {
            "shift_tracking_required": bool(policy and policy.shift_tracking_required and policy.is_active),
            "on_shift": False,
            "policy": policy,
            "server_time": now,
            "local_time": local_now,
            "today": today,
            "totals": totals,
            "can_start": False,
            "reason": "not_required",
        }

    window = resolve_day_window(policy, today)
    totals = day_totals(user, today, now)
    can_start = False
    reason = ""
    if session is not None:
        reason = "active"
    elif not window.is_working_day:
        reason = "disallowed_day"
    else:
        now_time = local_now.time().replace(tzinfo=None)
        if now_time < window.start_time:
            reason = "too_early"
        elif now_time >= window.end_time:
            reason = "too_late"
        else:
            can_start = True
            reason = "ok"

    return {
        "shift_tracking_required": True,
        "on_shift": session is not None,
        "policy": policy,
        "session": session,
        "server_time": now,
        "local_time": local_now,
        "today": today,
        "window": window,
        "totals": totals,
        "current_session_seconds": credited_seconds_so_far(session, now) if session else 0,
        "can_start": can_start,
        "reason": reason,
    }


def end_shift_preview(user, now: datetime | None = None) -> dict:
    now = now or timezone.now()
    reconcile_active_session(user, now=now)
    session = active_session(user)
    if session is None:
        raise ShiftError("no_active_session", "You do not have an active work session.")
    today = session.work_date
    current = credited_seconds_so_far(session, now)
    totals = day_totals(user, today, now)
    target_seconds = totals["target_seconds"]
    display_name = user.get_full_name() or user.username
    return {
        "employee_name": display_name,
        "current_session_seconds": current,
        "credited_seconds_today": totals["credited_seconds"],
        "target_seconds": target_seconds,
        "remaining_seconds": max(0, target_seconds - totals["credited_seconds"]),
        "overtime_seconds": max(0, totals["credited_seconds"] - target_seconds),
        "session_count": totals["session_count"],
    }


def close_stale_sessions(now: datetime | None = None, request=None) -> dict:
    """Idempotent sweep used by the scheduler / management command.

    Closes every session whose inactivity or 9:00 PM cap has passed. Safe to run
    repeatedly and concurrently (each session is row-locked individually).
    """
    now = now or timezone.now()
    closed = 0
    inspected = 0
    candidate_ids = list(
        WorkSession.objects.filter(ended_at__isnull=True).values_list("pk", flat=True)
    )
    for pk in candidate_ids:
        with transaction.atomic():
            session = WorkSession.objects.select_for_update().filter(pk=pk, ended_at__isnull=True).first()
            if session is None:
                continue
            inspected += 1
            _end, reason = effective_close(session, now)
            if reason is not None:
                reconcile_session(session, now=now, request=request)
                closed += 1
    return {"inspected": inspected, "closed": closed, "at": now}
