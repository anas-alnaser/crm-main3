from datetime import time, timedelta

from django.utils import timezone

from crm.apitestbase import APITestBase
from leads.models import Lead, LeadStatus
from workforce import metrics
from workforce.models import EmployeeWorkPolicy, WorkSession
from workforce.timezones import local_date


class WorkforceMetricsTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.employee = self.make_sales(username="emp")
        self.policy = EmployeeWorkPolicy.objects.create(user=self.employee, daily_target_minutes=180)
        self.today = local_date()
        # Two closed sessions today: 2h + 2h30m = 4h30m (overtime over 3h target).
        self._closed_session(minutes=120)
        self._closed_session(minutes=150, inactivity=True)

    def _closed_session(self, minutes, inactivity=False):
        now = timezone.now()
        return WorkSession.objects.create(
            employee=self.employee, policy=self.policy, timezone="Asia/Amman", daily_target_minutes=180,
            window_start_time=time(9, 0), window_end_time=time(21, 0),
            started_at=now - timedelta(minutes=minutes + 1), ended_at=now,
            last_activity_at=now, work_date=self.today,
            credited_seconds=minutes * 60,
            closing_reason="inactivity" if inactivity else "manual_end",
            auto_closed=inactivity,
        )

    def test_work_metrics_credited_and_overtime(self):
        data = metrics.work_metrics(self.employee, self.today, self.today)
        self.assertEqual(data["credited_seconds"], (120 + 150) * 60)
        self.assertEqual(data["session_count"], 2)
        self.assertEqual(data["inactivity_closures"], 1)
        self.assertEqual(data["manual_closures"], 1)

    def test_work_metrics_observations_mention_inactivity(self):
        data = metrics.work_metrics(self.employee, self.today, self.today)
        self.assertTrue(any("inactivity" in obs.lower() for obs in data["observations"]))

    def test_lead_metrics(self):
        Lead.objects.create(name="A", original_phone="1", normalized_phone="+1", assigned_to=self.employee, status=LeadStatus.INTERESTED)
        Lead.objects.create(name="B", original_phone="2", normalized_phone="+2", assigned_to=self.employee, status=LeadStatus.NOT_INTERESTED)
        data = metrics.lead_metrics(self.employee, self.today, self.today)
        self.assertEqual(data["assigned"], 2)
        self.assertEqual(data["interested"], 1)
        self.assertEqual(data["not_interested"], 1)

    def test_daily_breakdown_has_row_per_day(self):
        rows = metrics.daily_breakdown(self.employee, self.today - timedelta(days=2), self.today)
        self.assertEqual(len(rows), 3)
        today_row = next(r for r in rows if r["date"] == self.today)
        self.assertEqual(today_row["credited_seconds"], (120 + 150) * 60)

    def test_salary_summary_no_auto_deduction(self):
        self.policy.basic_salary = 150
        self.policy.save()
        data = metrics.salary_summary(self.employee)
        self.assertTrue(data["configured"])
        self.assertEqual(data["basic_salary"], "150.00")
        self.assertIn("No payroll deduction", data["note"])

    def test_dashboard_endpoint_admin_only(self):
        self.auth(self.employee)
        resp = self.client.get(f"/api/workforce/dashboard/?employee={self.employee.id}")
        self.assertEqual(resp.status_code, 403)

        self.auth(self.admin)
        resp = self.client.get(f"/api/workforce/dashboard/?employee={self.employee.id}&period=current_month")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("work", resp.data)
        self.assertIn("leads", resp.data)
        self.assertIn("crm", resp.data)
        self.assertIn("daily", resp.data)

    def test_period_resolution_previous_month(self):
        start, end = metrics.resolve_period({"period": "previous_month"})
        self.assertEqual(start.day, 1)
        self.assertLess(end, self.today.replace(day=1))
