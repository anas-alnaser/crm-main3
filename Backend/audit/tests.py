from datetime import time

from django.utils import timezone

from audit.models import AuditCategory, AuditEvent, AuditSource
from audit.redaction import redact
from audit.services import record_event
from crm.apitestbase import APITestBase
from workforce.models import EmployeeWorkPolicy, WorkSession
from workforce.timezones import local_date


def active_session(employee, policy):
    now = timezone.now()
    return WorkSession.objects.create(
        employee=employee, policy=policy, timezone="Asia/Amman", daily_target_minutes=180,
        window_start_time=time(0, 1), window_end_time=time(23, 59),
        started_at=now, last_activity_at=now, work_date=local_date(),
    )


class RedactionTests(APITestBase):
    def test_redacts_sensitive_keys(self):
        data = redact({"password": "secret", "name": "Alice", "api_key": "abc", "nested": {"jwt": "x", "ok": 1}})
        self.assertEqual(data["password"], "***redacted***")
        self.assertEqual(data["api_key"], "***redacted***")
        self.assertEqual(data["name"], "Alice")
        self.assertEqual(data["nested"]["jwt"], "***redacted***")
        self.assertEqual(data["nested"]["ok"], 1)

    def test_redacts_tokens_and_connection_strings(self):
        data = redact({"authorization": "Bearer x", "database_url": "postgres://u:p@h/db", "refresh_token": "r"})
        self.assertEqual(data["authorization"], "***redacted***")
        self.assertEqual(data["database_url"], "***redacted***")
        self.assertEqual(data["refresh_token"], "***redacted***")

    def test_redacts_inside_lists(self):
        data = redact({"items": [{"secret": "x", "id": 1}]})
        self.assertEqual(data["items"][0]["secret"], "***redacted***")
        self.assertEqual(data["items"][0]["id"], 1)


class AuditRecordingTests(APITestBase):
    def test_record_event_redacts_metadata(self):
        user = self.make_admin()
        event = record_event(
            action="test.event", category=AuditCategory.CRM, user=user,
            metadata={"password": "leak", "field": "value"},
        )
        self.assertEqual(event.metadata["password"], "***redacted***")
        self.assertEqual(event.metadata["field"], "value")

    def test_shift_events_recorded(self):
        from workforce import services
        from workforce.tests import amman, SUNDAY

        employee = self.make_sales(username="emp")
        EmployeeWorkPolicy.objects.create(user=employee)
        services.start_shift(employee, now=amman(SUNDAY, 9, 0))
        self.assertTrue(AuditEvent.objects.filter(action="shift.started", user=employee).exists())


class AuditViewerTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.sales = self.make_sales(username="rep")
        record_event(action="record.created", category=AuditCategory.CRM, user=self.sales, entity_type="Client", entity_id="1", summary="Created")
        record_event(action="lead.converted", category=AuditCategory.LEAD, user=self.sales, entity_type="Lead", entity_id="2", summary="Converted")

    def test_admin_can_view_audit(self):
        self.auth(self.admin)
        resp = self.client.get("/api/audit-events/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data["count"], 2)

    def test_sales_cannot_view_audit(self):
        self.auth(self.sales)
        self.assertEqual(self.client.get("/api/audit-events/").status_code, 403)

    def test_category_filter(self):
        self.auth(self.admin)
        resp = self.client.get("/api/audit-events/?category=lead")
        self.assertTrue(all(row["category"] == "lead" for row in resp.data["results"]))

    def test_csv_export(self):
        self.auth(self.admin)
        resp = self.client.get("/api/audit-events/export/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("created_at", resp.content.decode())

    def test_privacy_notice_available(self):
        self.auth(self.sales)
        resp = self.client.get("/api/audit-events/privacy-notice/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("never records", resp.data["notice"].lower())


class TelemetryTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.user = self.make_sales(username="rep")

    def test_whitelisted_event_accepted(self):
        self.auth(self.user)
        resp = self.client.post("/api/telemetry/", {"action": "page.opened", "entity_type": "leads"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(AuditEvent.objects.filter(action="page.opened", source=AuditSource.CLIENT).exists())

    def test_unknown_event_rejected(self):
        self.auth(self.user)
        resp = self.client.post("/api/telemetry/", {"action": "keystroke.logged"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_duplicate_deduplicated(self):
        self.auth(self.user)
        self.client.post("/api/telemetry/", {"action": "lead.opened", "entity_id": "5"}, format="json")
        resp = self.client.post("/api/telemetry/", {"action": "lead.opened", "entity_id": "5"}, format="json")
        self.assertFalse(resp.data.get("recorded"))
        self.assertTrue(resp.data.get("deduplicated"))
