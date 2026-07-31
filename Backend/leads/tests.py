import io
from datetime import time

from django.utils import timezone
from openpyxl import Workbook

from crm.apitestbase import APITestBase
from leads.importer import ImportError_, parse_workbook
from leads.models import Lead, LeadContactAttempt, LeadStatus
from leads.phone import normalize_phone
from leads.services import LeadError, convert_lead, reopen_lead
from workforce.models import EmployeeWorkPolicy, WorkSession
from workforce.timezones import local_date


def make_xlsx(rows, headers=("Name", "Phone")):
    wb = Workbook()
    ws = wb.active
    ws.append(list(headers))
    for row in rows:
        ws.append(list(row))
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    buffer.name = "leads.xlsx"
    return buffer


def active_session(employee, policy):
    now = timezone.now()
    return WorkSession.objects.create(
        employee=employee, policy=policy, timezone="Asia/Amman", daily_target_minutes=180,
        window_start_time=time(0, 1), window_end_time=time(23, 59),
        started_at=now, last_activity_at=now, work_date=local_date(),
    )


class PhoneNormalizationTests(APITestBase):
    def test_jordan_mobile_national(self):
        self.assertEqual(normalize_phone("0790123456")[0], "+962790123456")

    def test_jordan_with_country_code(self):
        self.assertEqual(normalize_phone("+962790123456")[0], "+962790123456")

    def test_double_zero_prefix(self):
        self.assertEqual(normalize_phone("00962790123456")[0], "+962790123456")

    def test_spaces_and_dashes_stripped(self):
        self.assertEqual(normalize_phone("079-012 3456")[0], "+962790123456")

    def test_empty_returns_blank(self):
        self.assertEqual(normalize_phone("")[0], "")

    def test_duplicate_spellings_collide(self):
        self.assertEqual(normalize_phone("0790123456")[0], normalize_phone("+962 790 123 456")[0])


class ImportParsingTests(APITestBase):
    def test_valid_import(self):
        result = parse_workbook(make_xlsx([("Alice", "0790000001"), ("Bob", "0790000002")]))
        self.assertEqual(len(result.imported), 2)
        self.assertEqual(len(result.invalid), 0)

    def test_missing_headers(self):
        with self.assertRaises(ImportError_) as ctx:
            parse_workbook(make_xlsx([("Alice", "0790000001")], headers=("Full", "Contact")))
        self.assertEqual(ctx.exception.code, "missing_headers")

    def test_missing_name_is_invalid(self):
        result = parse_workbook(make_xlsx([("", "0790000001")]))
        self.assertEqual(len(result.invalid), 1)

    def test_invalid_phone(self):
        result = parse_workbook(make_xlsx([("Alice", "abc")]))
        self.assertEqual(len(result.invalid), 1)

    def test_duplicate_within_file(self):
        result = parse_workbook(make_xlsx([("Alice", "0790000001"), ("Al", "0790000001")]))
        self.assertEqual(len(result.imported), 1)
        self.assertEqual(len(result.duplicates), 1)

    def test_duplicate_against_existing(self):
        Lead.objects.create(name="Existing", original_phone="0790000001", normalized_phone="+962790000001")
        result = parse_workbook(make_xlsx([("Alice", "0790000001")]))
        self.assertEqual(len(result.imported), 0)
        self.assertEqual(len(result.duplicates), 1)

    def test_formula_cell_rejected(self):
        result = parse_workbook(make_xlsx([("=cmd()", "0790000001")]))
        self.assertEqual(len(result.invalid), 1)

    def test_empty_rows_skipped(self):
        result = parse_workbook(make_xlsx([("", ""), ("Alice", "0790000009")]))
        self.assertEqual(len(result.imported), 1)
        self.assertEqual(result.total_rows, 1)


class ImportUploadAPITests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.sales = self.make_sales(username="rep")

    def test_admin_uploads_and_assigns(self):
        self.auth(self.admin)
        resp = self.client.post(
            "/api/lead-imports/upload/",
            {"file": make_xlsx([("Alice", "0790000001"), ("Bob", "0790000002")]), "assigned_to": self.sales.id, "source": "IG"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["imported_count"], 2)
        self.assertEqual(resp.data["assigned_count"], 2)
        self.assertEqual(Lead.objects.filter(assigned_to=self.sales).count(), 2)

    def test_preview_does_not_persist(self):
        self.auth(self.admin)
        resp = self.client.post(
            "/api/lead-imports/upload/",
            {"file": make_xlsx([("Alice", "0790000001")]), "preview": "true"},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["preview"])
        self.assertEqual(Lead.objects.count(), 0)

    def test_sales_cannot_upload(self):
        self.auth(self.sales)
        resp = self.client.post(
            "/api/lead-imports/upload/",
            {"file": make_xlsx([("Alice", "0790000001")])},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 403)

    def test_bad_extension_rejected(self):
        self.auth(self.admin)
        bad = io.BytesIO(b"not a spreadsheet")
        bad.name = "leads.txt"
        resp = self.client.post("/api/lead-imports/upload/", {"file": bad}, format="multipart")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "bad_extension")


class LeadScopingAndWorkflowTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.rep = self.make_sales(username="rep")
        self.other = self.make_sales(username="other")
        self.policy = EmployeeWorkPolicy.objects.create(user=self.rep)
        self.session = active_session(self.rep, self.policy)
        self.lead = Lead.objects.create(name="Alice", original_phone="0790000001", normalized_phone="+962790000001", assigned_to=self.rep)

    def test_sales_sees_only_assigned(self):
        Lead.objects.create(name="Other", original_phone="0790000002", normalized_phone="+962790000002", assigned_to=self.other)
        self.auth(self.rep)
        rows = self.client.get("/api/leads/").data["results"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], self.lead.id)

    def test_sales_cannot_access_foreign_lead(self):
        foreign = Lead.objects.create(name="Other", original_phone="0790000002", normalized_phone="+962790000002", assigned_to=self.other)
        self.auth(self.rep)
        self.assertEqual(self.client.get(f"/api/leads/{foreign.id}/").status_code, 404)

    def test_contact_attempt_no_answer(self):
        self.auth(self.rep)
        resp = self.client.post(
            f"/api/leads/{self.lead.id}/contact/",
            {"method": "call", "outcome": "no_answer", "resulting_status": "no_answer"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, LeadStatus.NO_ANSWER)
        self.assertEqual(LeadContactAttempt.objects.filter(lead=self.lead).count(), 1)

    def test_follow_up_requires_date(self):
        self.auth(self.rep)
        resp = self.client.post(
            f"/api/leads/{self.lead.id}/contact/",
            {"method": "call", "outcome": "callback_requested", "resulting_status": "follow_up"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "follow_up_required")

    def test_off_shift_contact_denied(self):
        self.session.ended_at = timezone.now()
        self.session.save()
        self.auth(self.rep)
        resp = self.client.post(
            f"/api/leads/{self.lead.id}/contact/",
            {"method": "call", "outcome": "no_answer"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "off_shift")

    def test_lead_cannot_be_deleted(self):
        self.auth(self.admin)
        self.assertEqual(self.client.delete(f"/api/leads/{self.lead.id}/").status_code, 405)

    def test_overdue_follow_up_filter(self):
        self.lead.status = LeadStatus.FOLLOW_UP
        self.lead.follow_up_at = timezone.now() - timezone.timedelta(days=1)
        self.lead.save()
        self.auth(self.admin)
        rows = self.client.get("/api/leads/?overdue=true").data["results"]
        self.assertEqual(len(rows), 1)


class LeadConversionTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.rep = self.make_sales(username="rep")
        self.policy = EmployeeWorkPolicy.objects.create(user=self.rep)
        active_session(self.rep, self.policy)
        self.pipeline, self.stages = self.make_pipeline_with_stages()
        self.lead = Lead.objects.create(
            name="Alice", original_phone="0790000001", normalized_phone="+962790000001",
            assigned_to=self.rep, status=LeadStatus.INTERESTED,
        )

    def test_convert_creates_client(self):
        lead, client, deal = convert_lead(self.lead.id, self.rep)
        lead.refresh_from_db()
        self.assertEqual(lead.status, LeadStatus.CONVERTED)
        self.assertIsNotNone(client)
        self.assertEqual(lead.converted_client_id, client.id)
        self.assertIsNone(deal)

    def test_convert_with_deal(self):
        lead, client, deal = convert_lead(self.lead.id, self.rep, create_deal=True, deal_value="500")
        self.assertIsNotNone(deal)
        self.assertEqual(deal.company_id, client.id)

    def test_duplicate_conversion_prevented(self):
        convert_lead(self.lead.id, self.rep)
        with self.assertRaises(LeadError) as ctx:
            convert_lead(self.lead.id, self.rep)
        self.assertEqual(ctx.exception.code, "already_converted")

    def test_not_interested_blocks_conversion(self):
        self.lead.status = LeadStatus.NOT_INTERESTED
        self.lead.save()
        with self.assertRaises(LeadError) as ctx:
            convert_lead(self.lead.id, self.rep)
        self.assertEqual(ctx.exception.code, "terminal")

    def test_no_answer_conversion_requires_reason(self):
        self.lead.status = LeadStatus.NO_ANSWER
        self.lead.save()
        with self.assertRaises(LeadError) as ctx:
            convert_lead(self.lead.id, self.rep)
        self.assertEqual(ctx.exception.code, "reason_required")
        # With a reason it succeeds.
        lead, client, _ = convert_lead(self.lead.id, self.rep, reason="Customer called back later")
        self.assertEqual(lead.status, LeadStatus.CONVERTED)

    def test_existing_client_linking(self):
        existing = self.make_company(name="Alice")
        lead, client, _ = convert_lead(self.lead.id, self.rep, existing_client_id=existing.id)
        self.assertEqual(client.id, existing.id)

    def test_admin_reopen_with_reason(self):
        convert_lead(self.lead.id, self.rep)
        self.lead.refresh_from_db()
        reopen_lead(self.lead, self.admin, "Re-engaging the client")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, LeadStatus.NEW)
        self.assertEqual(self.lead.reopened_reason, "Re-engaging the client")

    def test_reopen_requires_reason(self):
        self.lead.status = LeadStatus.NOT_INTERESTED
        self.lead.save()
        with self.assertRaises(LeadError) as ctx:
            reopen_lead(self.lead, self.admin, "")
        self.assertEqual(ctx.exception.code, "reason_required")

    def test_convert_via_api(self):
        self.auth(self.rep)
        resp = self.client.post(f"/api/leads/{self.lead.id}/convert/", {"create_deal": True, "deal_value": "1000"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.data["client"])
        self.assertIsNotNone(resp.data["deal"])
