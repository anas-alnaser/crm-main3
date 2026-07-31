from datetime import time

from django.conf import settings
from django.db import models
from django.db.models import Q

from .timezones import SUNDAY_TO_THURSDAY, WEEKDAY_LABELS


def default_working_days():
    # Sunday–Thursday by default (see workforce.timezones).
    return list(SUNDAY_TO_THURSDAY)


class EmployeeWorkPolicy(models.Model):
    """Per-employee working policy: window, targets, salary, and whether shift
    tracking is enforced at all. Admins are only shift-tracked if an admin
    explicitly gives them a policy with ``shift_tracking_required=True``.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="work_policy",
        on_delete=models.CASCADE,
    )
    shift_tracking_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    timezone = models.CharField(max_length=64, default="Asia/Amman")

    employment_start_date = models.DateField(null=True, blank=True)
    employment_end_date = models.DateField(null=True, blank=True)

    # Monday=0 … Sunday=6 (Python weekday()); default Sunday–Thursday.
    working_days = models.JSONField(default=default_working_days)
    earliest_start_time = models.TimeField(default=time(9, 0))
    latest_end_time = models.TimeField(default=time(21, 0))

    daily_target_minutes = models.PositiveIntegerField(default=180)
    monthly_target_minutes = models.PositiveIntegerField(null=True, blank=True)

    basic_salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    salary_currency = models.CharField(max_length=3, default="JOD")
    overtime_allowed = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="modified_work_policies",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Employee work policy"
        verbose_name_plural = "Employee work policies"
        ordering = ["user__username"]

    def __str__(self):
        return f"Work policy for {self.user}"

    def working_day_labels(self):
        return [WEEKDAY_LABELS.get(day, str(day)) for day in sorted(self.working_days or [])]

    def allows_weekday(self, weekday: int) -> bool:
        return weekday in (self.working_days or [])


class WorkPolicyException(models.Model):
    """Admin-approved, date-specific override of a policy (extra day, custom
    window, or holiday)."""

    class ExceptionType(models.TextChoices):
        EXTRA_WORKING_DAY = "extra_working_day", "Extra working day"
        CUSTOM_WINDOW = "custom_window", "Custom start/end time"
        HOLIDAY = "holiday", "Holiday (day off)"
        ONE_DAY_OVERRIDE = "one_day_override", "One-day override"

    policy = models.ForeignKey(
        EmployeeWorkPolicy,
        related_name="exceptions",
        on_delete=models.CASCADE,
    )
    date = models.DateField()
    exception_type = models.CharField(max_length=32, choices=ExceptionType.choices)
    custom_start_time = models.TimeField(null=True, blank=True)
    custom_end_time = models.TimeField(null=True, blank=True)
    reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="approved_work_exceptions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["policy", "date"], name="one_exception_per_policy_date"),
        ]

    def __str__(self):
        return f"{self.exception_type} for {self.policy_id} on {self.date}"

    @property
    def is_day_off(self) -> bool:
        return self.exception_type == self.ExceptionType.HOLIDAY


class ClosingReason(models.TextChoices):
    MANUAL_END = "manual_end", "Manually ended"
    INACTIVITY = "inactivity", "Closed by inactivity"
    WORKING_WINDOW_ENDED = "working_window_ended", "Working window ended (9:00 PM)"
    ADMIN_CLOSED = "admin_closed", "Closed by administrator"
    POLICY_DISABLED = "policy_disabled", "Policy disabled"
    SYSTEM_RECONCILIATION = "system_reconciliation", "System reconciliation"


class WorkSession(models.Model):
    """A single work session. Multiple closed sessions per day are allowed; only
    one may be active (open) per employee, enforced by a partial unique index.

    All durations are server-authoritative and credited as whole integer
    seconds (never floating-point hours).
    """

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="work_sessions",
        on_delete=models.CASCADE,
    )
    policy = models.ForeignKey(
        EmployeeWorkPolicy,
        related_name="sessions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    # Snapshot of policy values at session start, so historical reporting and
    # the hard 9:00 PM cap are stable even if the policy changes later.
    timezone = models.CharField(max_length=64, default="Asia/Amman")
    daily_target_minutes = models.PositiveIntegerField(default=180)
    window_start_time = models.TimeField(default=time(9, 0))
    window_end_time = models.TimeField(default=time(21, 0))

    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField()
    # Local business date the session belongs to (Asia/Amman).
    work_date = models.DateField()

    closing_reason = models.CharField(max_length=32, choices=ClosingReason.choices, blank=True)
    credited_seconds = models.PositiveIntegerField(default=0)
    auto_closed = models.BooleanField(default=False)

    start_ip = models.GenericIPAddressField(null=True, blank=True)
    start_user_agent = models.CharField(max_length=400, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            # At most one open session per employee.
            models.UniqueConstraint(
                fields=["employee"],
                condition=Q(ended_at__isnull=True),
                name="one_active_session_per_employee",
            ),
        ]
        indexes = [
            models.Index(fields=["employee", "-started_at"]),
            models.Index(fields=["employee", "work_date"]),
            models.Index(fields=["ended_at"]),
        ]

    def __str__(self):
        state = "active" if self.is_active else self.closing_reason or "closed"
        return f"Session {self.pk} for {self.employee_id} ({state})"

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @property
    def credited_minutes(self) -> int:
        return self.credited_seconds // 60
