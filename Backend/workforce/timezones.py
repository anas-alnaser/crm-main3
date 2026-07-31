"""Business-timezone helpers for shift logic.

All timestamps are stored in UTC. Shift rules (working day, 9:00 AM–9:00 PM
window, day boundaries) are evaluated in the business timezone (``Asia/Amman``
by default, overridable per policy).

Weekday convention: Python's ``date.weekday()`` where Monday=0 … Sunday=6.
The requested default working week is Sunday–Thursday.
"""
from __future__ import annotations

from datetime import datetime, time
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

# Monday=0 … Sunday=6 (Python weekday()).
MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)

WEEKDAY_LABELS = {
    MONDAY: "Monday",
    TUESDAY: "Tuesday",
    WEDNESDAY: "Wednesday",
    THURSDAY: "Thursday",
    FRIDAY: "Friday",
    SATURDAY: "Saturday",
    SUNDAY: "Sunday",
}

# Requested default: Sunday through Thursday.
SUNDAY_TO_THURSDAY = [SUNDAY, MONDAY, TUESDAY, WEDNESDAY, THURSDAY]


def business_tzname(name: str | None = None) -> str:
    return name or getattr(settings, "BUSINESS_TIMEZONE", "Asia/Amman")


def business_tz(name: str | None = None) -> ZoneInfo:
    try:
        return ZoneInfo(business_tzname(name))
    except Exception:  # pragma: no cover - misconfiguration guard
        return ZoneInfo("Asia/Amman")


def to_business(dt: datetime, tzname: str | None = None) -> datetime:
    """Convert an aware datetime to the business timezone."""
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, dt_timezone.utc)
    return dt.astimezone(business_tz(tzname))


def business_now(tzname: str | None = None) -> datetime:
    return timezone.now().astimezone(business_tz(tzname))


def local_date(dt: datetime | None = None, tzname: str | None = None):
    """Return the local business date for ``dt`` (default: now)."""
    dt = dt or timezone.now()
    return to_business(dt, tzname).date()


def local_time(dt: datetime | None = None, tzname: str | None = None) -> time:
    dt = dt or timezone.now()
    return to_business(dt, tzname).timetz().replace(tzinfo=None)


def combine_local(date_value, time_value: time, tzname: str | None = None) -> datetime:
    """Build an aware UTC datetime from a local date + local time."""
    naive = datetime.combine(date_value, time_value)
    aware_local = naive.replace(tzinfo=business_tz(tzname))
    return aware_local.astimezone(dt_timezone.utc)


def parse_time(value: str) -> time:
    """Parse ``"HH:MM"`` (or ``"HH:MM:SS"``) into a ``time``."""
    parts = [int(p) for p in value.split(":")]
    while len(parts) < 3:
        parts.append(0)
    hour, minute, second = parts[:3]
    return time(hour=hour, minute=minute, second=second)
