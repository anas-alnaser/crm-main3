from datetime import date, time, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from crm.apitestbase import APITestBase
from workforce.models import (
    ClosingReason,
    EmployeeWorkPolicy,
    WorkPolicyException,
    WorkSession,
)
from workforce import services
from workforce.services import ShiftError
from workforce.timezones import combine_local, local_date

# A known Sunday (working day) and Friday (non-working) in Asia/Amman (UTC+3).
SUNDAY = date(2026, 8, 2)
FRIDAY = date(2026, 8, 7)


def amman(day, hour, minute=0):
    """UTC instant for a given Amman wall-clock time."""
    return combine_local(day, time(hour, minute), "Asia/Amman")


def wall_clock_active_session(employee, policy=None, minutes_ago=0):
    """Create an active session anchored to the current wall clock that will
    survive reconciliation regardless of when the test runs (window end 23:59,
    fresh activity)."""
    now = timezone.now()
    return WorkSession.objects.create(
        employee=employee, policy=policy, timezone="Asia/Amman", daily_target_minutes=180,
        window_start_time=time(0, 1), window_end_time=time(23, 59),
        started_at=now - timedelta(minutes=minutes_ago), last_activity_at=now,
        work_date=local_date(),
    )


class PolicyTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.employee = self.make_sales(username="emp")

    def test_policy_defaults_sunday_to_thursday(self):
        policy = EmployeeWorkPolicy.objects.create(user=self.employee)
        # Monday=0 … Sunday=6; Sunday–Thursday = {6,0,1,2,3}.
        self.assertEqual(set(policy.working_days), {6, 0, 1, 2, 3})
        self.assertEqual(policy.daily_target_minutes, 180)
        self.assertEqual(policy.earliest_start_time, time(9, 0))
        self.assertEqual(policy.latest_end_time, time(21, 0))
        self.assertTrue(policy.allows_weekday(6))  # Sunday
        self.assertFalse(policy.allows_weekday(4))  # Friday

    def test_admin_not_shift_required_without_policy(self):
        admin = self.make_admin(username="a2")
        self.assertFalse(services.is_shift_required(admin))


class ShiftStartTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.employee = self.make_sales(username="emp")
        self.policy = EmployeeWorkPolicy.objects.create(user=self.employee)

    def test_start_before_9am_rejected(self):
        with self.assertRaises(ShiftError) as ctx:
            services.start_shift(self.employee, now=amman(SUNDAY, 8, 30))
        self.assertEqual(ctx.exception.code, "too_early")

    def test_start_at_9am_accepted(self):
        session = services.start_shift(self.employee, now=amman(SUNDAY, 9, 0))
        self.assertTrue(session.is_active)
        self.assertEqual(session.work_date, SUNDAY)

    def test_start_before_9pm_accepted(self):
        session = services.start_shift(self.employee, now=amman(SUNDAY, 20, 59))
        self.assertTrue(session.is_active)

    def test_start_at_9pm_rejected(self):
        with self.assertRaises(ShiftError) as ctx:
            services.start_shift(self.employee, now=amman(SUNDAY, 21, 0))
        self.assertEqual(ctx.exception.code, "too_late")

    def test_start_on_disallowed_day_rejected(self):
        with self.assertRaises(ShiftError) as ctx:
            services.start_shift(self.employee, now=amman(FRIDAY, 10, 0))
        self.assertEqual(ctx.exception.code, "disallowed_day")

    def test_exception_day_allows_start(self):
        WorkPolicyException.objects.create(
            policy=self.policy, date=FRIDAY,
            exception_type=WorkPolicyException.ExceptionType.EXTRA_WORKING_DAY,
        )
        session = services.start_shift(self.employee, now=amman(FRIDAY, 10, 0))
        self.assertTrue(session.is_active)

    def test_holiday_exception_blocks_start(self):
        WorkPolicyException.objects.create(
            policy=self.policy, date=SUNDAY,
            exception_type=WorkPolicyException.ExceptionType.HOLIDAY,
        )
        with self.assertRaises(ShiftError) as ctx:
            services.start_shift(self.employee, now=amman(SUNDAY, 10, 0))
        self.assertEqual(ctx.exception.code, "disallowed_day")

    def test_inactive_policy_rejected(self):
        self.policy.is_active = False
        self.policy.save()
        with self.assertRaises(ShiftError) as ctx:
            services.start_shift(self.employee, now=amman(SUNDAY, 10, 0))
        self.assertEqual(ctx.exception.code, "policy_inactive")

    def test_duplicate_active_session_rejected(self):
        services.start_shift(self.employee, now=amman(SUNDAY, 9, 0))
        # Second start 5 minutes later, while the first is genuinely active.
        with self.assertRaises(ShiftError) as ctx:
            services.start_shift(self.employee, now=amman(SUNDAY, 9, 5))
        self.assertEqual(ctx.exception.code, "already_active")

    def test_partial_unique_constraint_blocks_two_active(self):
        services.start_shift(self.employee, now=amman(SUNDAY, 9, 0))
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkSession.objects.create(
                    employee=self.employee, timezone="Asia/Amman", daily_target_minutes=180,
                    window_start_time=time(9, 0), window_end_time=time(21, 0),
                    started_at=timezone.now(), last_activity_at=timezone.now(), work_date=SUNDAY,
                )


class MultiSessionAndOvertimeTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.employee = self.make_sales(username="emp")
        self.policy = EmployeeWorkPolicy.objects.create(user=self.employee)

    def test_multiple_sessions_same_day(self):
        # Three separate manual sessions the same day, all credited to the total.
        s1 = services.start_shift(self.employee, now=amman(SUNDAY, 9, 0))
        services.end_shift(self.employee, now=amman(SUNDAY, 10, 0))
        s2 = services.start_shift(self.employee, now=amman(SUNDAY, 14, 0))
        services.end_shift(self.employee, now=amman(SUNDAY, 15, 0))
        s3 = services.start_shift(self.employee, now=amman(SUNDAY, 19, 30))
        services.end_shift(self.employee, now=amman(SUNDAY, 20, 0))
        self.assertNotEqual(s1.id, s2.id)
        self.assertNotEqual(s2.id, s3.id)
        totals = services.day_totals(self.employee, SUNDAY, now=amman(SUNDAY, 20, 30))
        # 60 + 60 + 30 = 150 minutes credited across the day.
        self.assertEqual(totals["credited_seconds"], 150 * 60)
        self.assertEqual(totals["session_count"], 3)

    def test_overtime_beyond_daily_target(self):
        services.start_shift(self.employee, now=amman(SUNDAY, 9, 0))
        # 4 hours > 3 hour target -> 1h overtime; not blocked at 3h.
        services.end_shift(self.employee, now=amman(SUNDAY, 13, 0))
        totals = services.day_totals(self.employee, SUNDAY, now=amman(SUNDAY, 13, 30))
        self.assertEqual(totals["credited_seconds"], 4 * 3600)
        self.assertEqual(totals["overtime_seconds"], 3600)  # 4h - 3h target

    def test_manual_end_credits_elapsed(self):
        services.start_shift(self.employee, now=amman(SUNDAY, 9, 0))
        session = services.end_shift(self.employee, now=amman(SUNDAY, 11, 30))
        self.assertEqual(session.closing_reason, ClosingReason.MANUAL_END)
        self.assertEqual(session.credited_seconds, 150 * 60)
        self.assertFalse(session.auto_closed)

    def test_end_preview_totals(self):
        services.start_shift(self.employee, now=amman(SUNDAY, 9, 0))
        # Keep the session active with a heartbeat within the 10-min window.
        services.record_heartbeat(self.employee, now=amman(SUNDAY, 9, 5))
        preview = services.end_shift_preview(self.employee, now=amman(SUNDAY, 9, 10))
        # 9:00 -> 9:10 = 10 minutes credited so far.
        self.assertEqual(preview["current_session_seconds"], 10 * 60)
        self.assertEqual(preview["credited_seconds_today"], 10 * 60)
        self.assertEqual(preview["employee_name"], self.employee.username)


class InactivityAndCapTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.employee = self.make_sales(username="emp")
        self.policy = EmployeeWorkPolicy.objects.create(user=self.employee)

    def test_ten_minute_inactivity_closes_and_credits_full_ten(self):
        services.start_shift(self.employee, now=amman(SUNDAY, 14, 0))
        # Last activity at 14:00; no heartbeats. Reconcile at 14:30.
        services.reconcile_active_session(self.employee, now=amman(SUNDAY, 14, 30))
        session = WorkSession.objects.get(employee=self.employee)
        self.assertFalse(session.is_active)
        self.assertEqual(session.closing_reason, ClosingReason.INACTIVITY)
        # Credited exactly start -> last_activity + 10 min = 14:00 -> 14:10.
        self.assertEqual(session.credited_seconds, 10 * 60)
        self.assertTrue(session.auto_closed)

    def test_inactivity_uses_last_activity_plus_ten(self):
        services.start_shift(self.employee, now=amman(SUNDAY, 14, 0))
        # Heartbeat at 14:05 extends last_activity.
        services.record_heartbeat(self.employee, now=amman(SUNDAY, 14, 5))
        services.reconcile_active_session(self.employee, now=amman(SUNDAY, 14, 40))
        session = WorkSession.objects.get(employee=self.employee)
        # start 14:00 -> last_activity 14:05 + 10 = 14:15 -> 15 min credited.
        self.assertEqual(session.credited_seconds, 15 * 60)

    def test_9pm_hard_cap_credit(self):
        services.start_shift(self.employee, now=amman(SUNDAY, 20, 45))
        # Active with heartbeat near 9pm (within the 10-min window); reconcile after 9pm.
        services.record_heartbeat(self.employee, now=amman(SUNDAY, 20, 52))
        services.reconcile_active_session(self.employee, now=amman(SUNDAY, 21, 30))
        session = WorkSession.objects.get(employee=self.employee)
        self.assertFalse(session.is_active)
        self.assertEqual(session.closing_reason, ClosingReason.WORKING_WINDOW_ENDED)
        # Credited 20:45 -> 21:00 = 15 min; nothing after 9pm.
        self.assertEqual(session.credited_seconds, 15 * 60)

    def test_inactivity_capped_at_9pm(self):
        services.start_shift(self.employee, now=amman(SUNDAY, 20, 55))
        # last_activity 20:55; +10 = 21:05 which exceeds 9pm -> cap at 21:00.
        services.reconcile_active_session(self.employee, now=amman(SUNDAY, 21, 30))
        session = WorkSession.objects.get(employee=self.employee)
        self.assertEqual(session.closing_reason, ClosingReason.WORKING_WINDOW_ENDED)
        self.assertEqual(session.credited_seconds, 5 * 60)  # 20:55 -> 21:00

    def test_reconciliation_idempotent(self):
        services.start_shift(self.employee, now=amman(SUNDAY, 14, 0))
        services.reconcile_active_session(self.employee, now=amman(SUNDAY, 14, 30))
        session = WorkSession.objects.get(employee=self.employee)
        credited = session.credited_seconds
        # Running again must not change anything.
        services.reconcile_active_session(self.employee, now=amman(SUNDAY, 15, 0))
        services.close_stale_sessions(now=amman(SUNDAY, 16, 0))
        session.refresh_from_db()
        self.assertEqual(session.credited_seconds, credited)

    def test_scheduled_close_stale_sessions(self):
        services.start_shift(self.employee, now=amman(SUNDAY, 14, 0))
        result = services.close_stale_sessions(now=amman(SUNDAY, 14, 30))
        self.assertEqual(result["closed"], 1)
        session = WorkSession.objects.get(employee=self.employee)
        self.assertFalse(session.is_active)

    def test_laptop_disappearance_scenario(self):
        # Employee's laptop sleeps: no heartbeats at all after start.
        services.start_shift(self.employee, now=amman(SUNDAY, 15, 0))
        # Much later a request comes in / scheduler runs.
        services.close_stale_sessions(now=amman(SUNDAY, 18, 0))
        session = WorkSession.objects.get(employee=self.employee)
        self.assertEqual(session.closing_reason, ClosingReason.INACTIVITY)
        self.assertEqual(session.credited_seconds, 10 * 60)

    def test_heartbeat_after_expiry_closes_instead_of_extending(self):
        services.start_shift(self.employee, now=amman(SUNDAY, 14, 0))
        # A late heartbeat 20 minutes later must not resurrect the session.
        session = services.record_heartbeat(self.employee, now=amman(SUNDAY, 14, 20))
        self.assertFalse(session.is_active)
        self.assertEqual(session.closing_reason, ClosingReason.INACTIVITY)


class ShiftAPITests(APITestBase):
    def setUp(self):
        super().setUp()
        self.employee = self.make_sales(username="emp")
        self.policy = EmployeeWorkPolicy.objects.create(user=self.employee)
        self.company = self.make_company()
        self.pipeline, self.stages = self.make_pipeline_with_stages()

    def test_off_shift_mutation_denied(self):
        self.auth(self.employee)
        resp = self.client.post("/api/clients/", {"name": "New Co"}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "off_shift")

    def test_off_shift_read_allowed(self):
        self.auth(self.employee)
        resp = self.client.get("/api/clients/")
        self.assertEqual(resp.status_code, 200)

    def test_on_shift_mutation_allowed(self):
        # Deterministic active session (independent of wall-clock time).
        wall_clock_active_session(self.employee, self.policy)
        self.auth(self.employee)
        resp = self.client.post("/api/clients/", {"name": "New Co"}, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_admin_exempt_from_shift_block(self):
        admin = self.make_admin(username="adm")
        self.auth(admin)
        resp = self.client.post("/api/clients/", {"name": "Admin Co"}, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_start_and_end_via_api(self):
        # Build an active session, then end via API preview + end.
        wall_clock_active_session(self.employee, self.policy, minutes_ago=45)
        self.auth(self.employee)
        preview = self.client.get("/api/workforce/shift/end/preview/")
        self.assertEqual(preview.status_code, 200)
        self.assertIn("message", preview.data)
        end = self.client.post("/api/workforce/shift/end/")
        self.assertEqual(end.status_code, 200)
        self.assertFalse(end.data["on_shift"])

    def test_heartbeat_endpoint(self):
        wall_clock_active_session(self.employee, self.policy, minutes_ago=1)
        self.auth(self.employee)
        resp = self.client.post("/api/workforce/shift/heartbeat/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["on_shift"])


class AdminCloseAndForeignAccessTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.employee = self.make_sales(username="emp")
        self.other = self.make_sales(username="other")
        self.policy = EmployeeWorkPolicy.objects.create(user=self.employee)
        self.session = wall_clock_active_session(self.employee, self.policy, minutes_ago=30)

    def test_admin_can_close_session(self):
        self.auth(self.admin)
        resp = self.client.post(f"/api/work-sessions/{self.session.id}/close/")
        self.assertEqual(resp.status_code, 200)
        self.session.refresh_from_db()
        self.assertEqual(self.session.closing_reason, ClosingReason.ADMIN_CLOSED)
        self.assertFalse(self.session.is_active)

    def test_sales_cannot_list_sessions(self):
        self.auth(self.other)
        resp = self.client.get("/api/work-sessions/")
        self.assertEqual(resp.status_code, 403)

    def test_policy_management_admin_only(self):
        self.auth(self.other)
        resp = self.client.get("/api/work-policies/")
        self.assertEqual(resp.status_code, 403)
        self.auth(self.admin)
        self.assertEqual(self.client.get("/api/work-policies/").status_code, 200)
