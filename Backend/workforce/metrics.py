"""Admin workforce & employee-performance metrics.

Aggregates three views of an employee over a date range: work (from sessions),
leads (from the leads app), and CRM activity (from the core apps + audit trail).
All time is credited in whole seconds and reported both raw and humanized.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.utils import timezone

from activities.models import Activity
from audit.models import AuditEvent
from clients.models import Client
from leads.models import Lead, LeadContactAttempt, LeadStatus
from meetings.models import Meeting
from projects.models import Project
from sales.models import Deal
from tasks.models import Task

from .models import ClosingReason, WorkSession
from .serializers import humanize_seconds
from .services import get_policy
from .timezones import combine_local, local_date


def _range_bounds(tzname, start: date, end: date):
    start_dt = combine_local(start, time(0, 0), tzname)
    end_dt = combine_local(end + timedelta(days=1), time(0, 0), tzname)
    return start_dt, end_dt


def _expected_workdays(policy, start: date, end: date) -> int:
    if policy is None:
        return 0
    working = set(policy.working_days or [])
    holidays = set(
        policy.exceptions.filter(
            date__gte=start, date__lte=end, exception_type="holiday"
        ).values_list("date", flat=True)
    )
    extra = set(
        policy.exceptions.filter(
            date__gte=start, date__lte=end,
            exception_type__in=["extra_working_day", "one_day_override"],
        ).values_list("date", flat=True)
    )
    count = 0
    cursor = start
    while cursor <= end:
        is_working = cursor.weekday() in working or cursor in extra
        if is_working and cursor not in holidays:
            count += 1
        cursor += timedelta(days=1)
    return count


def work_metrics(employee, start: date, end: date, now: datetime | None = None) -> dict:
    now = now or timezone.now()
    policy = get_policy(employee)
    sessions = list(WorkSession.objects.filter(employee=employee, work_date__gte=start, work_date__lte=end))

    credited = sum(s.credited_seconds for s in sessions)
    daily_target = policy.daily_target_minutes if policy else 180
    expected_days = _expected_workdays(policy, start, end)
    expected_seconds = expected_days * daily_target * 60

    days_worked = len({s.work_date for s in sessions if s.credited_seconds > 0})
    closures = {reason: 0 for reason, _ in ClosingReason.choices}
    for s in sessions:
        if s.closing_reason:
            closures[s.closing_reason] = closures.get(s.closing_reason, 0) + 1

    durations = [s.credited_seconds for s in sessions]
    longest = max(durations) if durations else 0
    avg = int(credited / len(sessions)) if sessions else 0

    first_start = min((s.started_at for s in sessions), default=None)
    last_end = max((s.ended_at for s in sessions if s.ended_at), default=None)

    active = WorkSession.objects.filter(employee=employee, ended_at__isnull=True).exists()

    target_completion = round((credited / expected_seconds) * 100, 1) if expected_seconds else 0.0

    return {
        "expected_seconds": expected_seconds,
        "expected_display": humanize_seconds(expected_seconds),
        "credited_seconds": credited,
        "credited_display": humanize_seconds(credited),
        "remaining_seconds": max(0, expected_seconds - credited),
        "remaining_display": humanize_seconds(max(0, expected_seconds - credited)),
        "overtime_seconds": max(0, credited - expected_seconds),
        "overtime_display": humanize_seconds(max(0, credited - expected_seconds)),
        "target_completion_percent": target_completion,
        "session_count": len(sessions),
        "average_session_seconds": avg,
        "average_session_display": humanize_seconds(avg),
        "longest_session_seconds": longest,
        "longest_session_display": humanize_seconds(longest),
        "manual_closures": closures.get(ClosingReason.MANUAL_END, 0),
        "inactivity_closures": closures.get(ClosingReason.INACTIVITY, 0),
        "window_closures": closures.get(ClosingReason.WORKING_WINDOW_ENDED, 0),
        "admin_closures": closures.get(ClosingReason.ADMIN_CLOSED, 0),
        "days_worked": days_worked,
        "expected_workdays": expected_days,
        "missed_expected_days": max(0, expected_days - days_worked),
        "first_start": first_start,
        "last_end": last_end,
        "current_shift_active": active,
        "observations": _work_observations(employee, closures),
    }


def _work_observations(employee, closures) -> list[str]:
    name = employee.get_full_name() or employee.username
    notes = []
    if closures.get(ClosingReason.INACTIVITY, 0):
        notes.append(f"{name} had {closures[ClosingReason.INACTIVITY]} inactivity closure(s) during this period.")
    if closures.get(ClosingReason.WORKING_WINDOW_ENDED, 0):
        notes.append(f"{name} had {closures[ClosingReason.WORKING_WINDOW_ENDED]} session(s) closed at the 9:00 PM boundary.")
    if closures.get(ClosingReason.ADMIN_CLOSED, 0):
        notes.append(f"{name} had {closures[ClosingReason.ADMIN_CLOSED]} session(s) closed by an administrator.")
    return notes


def lead_metrics(employee, start: date, end: date, tzname=None) -> dict:
    start_dt, end_dt = _range_bounds(tzname, start, end)
    assigned = Lead.objects.filter(assigned_to=employee)
    period_assigned = assigned.filter(created_at__gte=start_dt, created_at__lt=end_dt)
    attempts = LeadContactAttempt.objects.filter(employee=employee, created_at__gte=start_dt, created_at__lt=end_dt)
    converted = assigned.filter(status=LeadStatus.CONVERTED, converted_at__gte=start_dt, converted_at__lt=end_dt)
    converted_count = converted.count()
    contacted_leads = attempts.values("lead").distinct().count()

    deals_from_leads = Deal.objects.filter(source_leads__assigned_to=employee).distinct()
    return {
        "assigned": assigned.count(),
        "assigned_in_period": period_assigned.count(),
        "viewed": assigned.filter(first_viewed_at__isnull=False).count(),
        "contacted": contacted_leads,
        "contact_attempts": attempts.count(),
        "no_answer": assigned.filter(status=LeadStatus.NO_ANSWER).count(),
        "follow_ups_scheduled": assigned.filter(follow_up_at__isnull=False).count(),
        "overdue_follow_ups": assigned.filter(status=LeadStatus.FOLLOW_UP, follow_up_at__lt=timezone.now()).count(),
        "interested": assigned.filter(status=LeadStatus.INTERESTED).count(),
        "not_interested": assigned.filter(status=LeadStatus.NOT_INTERESTED).count(),
        "converted": converted_count,
        "conversion_rate": round((converted_count / assigned.count()) * 100, 1) if assigned.count() else 0.0,
        "clients_created": converted.filter(converted_client__isnull=False).count(),
        "deals_created_from_leads": deals_from_leads.count(),
        "deals_won_from_leads": deals_from_leads.filter(status=Deal.Status.WON).count(),
    }


def crm_metrics(employee, start: date, end: date, tzname=None) -> dict:
    start_dt, end_dt = _range_bounds(tzname, start, end)

    def in_range(qs, field="created_at"):
        return qs.filter(**{f"{field}__gte": start_dt, f"{field}__lt": end_dt})

    audit_qs = AuditEvent.objects.filter(user=employee, created_at__gte=start_dt, created_at__lt=end_dt)
    deals = Deal.objects.filter(owner=employee)
    return {
        "companies_created": in_range(Client.objects.filter(created_by=employee)).count(),
        "projects_created": in_range(Project.objects.filter(created_by=employee)).count(),
        "tasks_created": in_range(Task.objects.filter(created_by=employee)).count(),
        "tasks_completed": in_range(Task.objects.filter(created_by=employee, status="done"), "updated_at").count(),
        "activities_logged": in_range(Activity.objects.filter(created_by=employee)).count(),
        "meetings_created": in_range(Meeting.objects.filter(owner=employee)).count(),
        "meetings_completed": in_range(Meeting.objects.filter(owner=employee, status="completed"), "updated_at").count(),
        "deals_created": in_range(deals).count(),
        "deals_moved": audit_qs.filter(action="deal.moved").count(),
        "deals_won": deals.filter(status=Deal.Status.WON, closed_at__gte=start_dt, closed_at__lt=end_dt).count(),
        "important_edits": audit_qs.filter(action="record.updated").count(),
    }


def daily_breakdown(employee, start: date, end: date, now: datetime | None = None) -> list[dict]:
    now = now or timezone.now()
    policy = get_policy(employee)
    tzname = policy.timezone if policy else None
    daily_target = policy.daily_target_minutes if policy else 180
    target_seconds = daily_target * 60
    working = set(policy.working_days if policy else [])

    rows = []
    cursor = start
    while cursor <= end:
        start_dt, end_dt = _range_bounds(tzname, cursor, cursor)
        sessions = list(WorkSession.objects.filter(employee=employee, work_date=cursor))
        credited = sum(s.credited_seconds for s in sessions)
        expected = target_seconds if cursor.weekday() in working else 0
        inactivity = sum(1 for s in sessions if s.closing_reason == ClosingReason.INACTIVITY)
        first_start = min((s.started_at for s in sessions), default=None)
        last_end = max((s.ended_at for s in sessions if s.ended_at), default=None)

        leads_contacted = (
            LeadContactAttempt.objects.filter(employee=employee, created_at__gte=start_dt, created_at__lt=end_dt)
            .values("lead").distinct().count()
        )
        leads_converted = Lead.objects.filter(
            assigned_to=employee, status=LeadStatus.CONVERTED, converted_at__gte=start_dt, converted_at__lt=end_dt
        ).count()
        deals_created = Deal.objects.filter(owner=employee, created_at__gte=start_dt, created_at__lt=end_dt).count()
        deals_won = Deal.objects.filter(owner=employee, status=Deal.Status.WON, closed_at__gte=start_dt, closed_at__lt=end_dt).count()

        rows.append({
            "date": cursor,
            "expected_seconds": expected,
            "expected_display": humanize_seconds(expected),
            "credited_seconds": credited,
            "credited_display": humanize_seconds(credited),
            "delta_seconds": credited - expected,
            "remaining_or_overtime": humanize_seconds(abs(credited - expected)) + (" over" if credited > expected else " left" if expected else ""),
            "session_count": len(sessions),
            "first_start": first_start,
            "last_end": last_end,
            "inactivity_closures": inactivity,
            "leads_contacted": leads_contacted,
            "leads_converted": leads_converted,
            "deals_created": deals_created,
            "deals_won": deals_won,
        })
        cursor += timedelta(days=1)
    return rows


def salary_summary(employee) -> dict:
    policy = get_policy(employee)
    if policy is None:
        return {"configured": False}
    return {
        "configured": True,
        "basic_salary": str(policy.basic_salary) if policy.basic_salary is not None else None,
        "currency": policy.salary_currency,
        "monthly_target_minutes": policy.monthly_target_minutes,
        "monthly_target_display": humanize_seconds((policy.monthly_target_minutes or 0) * 60) if policy.monthly_target_minutes else None,
        "overtime_allowed": policy.overtime_allowed,
        # Deliberately NOT a payroll engine: no automatic deduction is applied.
        "note": "Informational only. No payroll deduction formula is applied.",
    }


def employee_dashboard(employee, start: date, end: date, now: datetime | None = None) -> dict:
    now = now or timezone.now()
    policy = get_policy(employee)
    tzname = policy.timezone if policy else None
    return {
        "employee": {
            "id": employee.id,
            "username": employee.username,
            "name": employee.get_full_name() or employee.username,
        },
        "period": {"start": start, "end": end},
        "work": work_metrics(employee, start, end, now),
        "leads": lead_metrics(employee, start, end, tzname),
        "crm": crm_metrics(employee, start, end, tzname),
        "salary": salary_summary(employee),
        "daily": daily_breakdown(employee, start, end, now),
    }


def resolve_period(params, tzname=None):
    """Resolve start/end dates from query params (period presets or custom range)."""
    today = local_date(tzname=tzname)
    period = params.get("period", "current_month")
    if period == "custom":
        start = _parse_date(params.get("start")) or today.replace(day=1)
        end = _parse_date(params.get("end")) or today
    elif period == "previous_month":
        first_this = today.replace(day=1)
        end = first_this - timedelta(days=1)
        start = end.replace(day=1)
    elif period == "last_7_days":
        start = today - timedelta(days=6)
        end = today
    else:  # current_month
        start = today.replace(day=1)
        end = today
    if end < start:
        start, end = end, start
    return start, end


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None
