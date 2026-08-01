"""Tests for superadmin-only permanent lead deletion."""
from django.utils import timezone

from crm.apitestbase import APITestBase
from audit.models import AuditEvent
from leads.models import Lead, LeadContactAttempt, LeadImportBatch, LeadStatus


class LeadPermanentDeleteTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.superadmin = self.make_superadmin(password="superpass123")
        self.admin = self.make_admin(username="normaladmin")
        self.sales = self.make_sales(username="rep")
        self.lead = Lead.objects.create(name="Alice", original_phone="0790000001", normalized_phone="+962790000001")
        self.attempt = LeadContactAttempt.objects.create(lead=self.lead, employee=self.sales, outcome="reached")

    def _delete(self, url_id, **body):
        return self.client.post(f"/api/leads/{url_id}/permanent-delete/", body, format="json")

    def _valid_body(self, lead_id):
        return {"current_password": "superpass123", "confirmation": "DELETE LEAD", "lead_id": lead_id}

    # -- authorization ----------------------------------------------------
    def test_anonymous_denied(self):
        self.assertEqual(self.client.get(f"/api/leads/{self.lead.id}/delete-impact/").status_code, 401)

    def test_sales_denied(self):
        self.auth(self.sales)
        self.assertEqual(self.client.get(f"/api/leads/{self.lead.id}/delete-impact/").status_code, 403)
        self.assertEqual(self._delete(self.lead.id, **self._valid_body(self.lead.id)).status_code, 403)

    def test_normal_admin_denied(self):
        # role=admin + is_staff but NOT is_superuser -> not a superadmin.
        self.auth(self.admin)
        self.assertEqual(self.client.get(f"/api/leads/{self.lead.id}/delete-impact/").status_code, 403)
        self.assertEqual(self._delete(self.lead.id, **self._valid_body(self.lead.id)).status_code, 403)

    def test_superuser_non_admin_role_denied(self):
        weird = self.make_sales(username="weird", is_staff=True, is_superuser=True)
        self.auth(weird)
        self.assertEqual(self.client.get(f"/api/leads/{self.lead.id}/delete-impact/").status_code, 403)

    # -- impact (read-only) ----------------------------------------------
    def test_superadmin_can_fetch_impact(self):
        self.auth(self.superadmin)
        resp = self.client.get(f"/api/leads/{self.lead.id}/delete-impact/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["lead_id"], self.lead.id)
        self.assertEqual(resp.data["contact_attempt_count"], 1)
        self.assertTrue(resp.data["deletion_allowed"])
        # No sensitive fields leak.
        self.assertNotIn("original_phone", resp.data)
        self.assertNotIn("notes", resp.data)

    def test_impact_performs_no_writes(self):
        self.auth(self.superadmin)
        self.client.get(f"/api/leads/{self.lead.id}/delete-impact/")
        self.assertTrue(Lead.objects.filter(pk=self.lead.id).exists())
        self.assertEqual(LeadContactAttempt.objects.count(), 1)

    # -- confirmation gating ---------------------------------------------
    def test_missing_password_rejected(self):
        self.auth(self.superadmin)
        resp = self._delete(self.lead.id, confirmation="DELETE LEAD", lead_id=self.lead.id)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "password_required")
        self.assertTrue(Lead.objects.filter(pk=self.lead.id).exists())

    def test_wrong_password_rejected(self):
        self.auth(self.superadmin)
        resp = self._delete(self.lead.id, current_password="nope", confirmation="DELETE LEAD", lead_id=self.lead.id)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "incorrect_password")
        self.assertTrue(Lead.objects.filter(pk=self.lead.id).exists())

    def test_missing_confirmation_rejected(self):
        self.auth(self.superadmin)
        resp = self._delete(self.lead.id, current_password="superpass123", lead_id=self.lead.id)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "confirmation_mismatch")

    def test_wrong_confirmation_rejected(self):
        self.auth(self.superadmin)
        resp = self._delete(self.lead.id, current_password="superpass123", confirmation="delete lead", lead_id=self.lead.id)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "confirmation_mismatch")

    def test_mismatched_lead_id_rejected(self):
        self.auth(self.superadmin)
        resp = self._delete(self.lead.id, current_password="superpass123", confirmation="DELETE LEAD", lead_id=self.lead.id + 999)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "id_mismatch")
        self.assertTrue(Lead.objects.filter(pk=self.lead.id).exists())

    def test_nonexistent_lead_404(self):
        self.auth(self.superadmin)
        self.assertEqual(self.client.get("/api/leads/999999/delete-impact/").status_code, 404)

    # -- successful deletion ---------------------------------------------
    def test_superadmin_can_delete_non_converted_lead(self):
        self.auth(self.superadmin)
        resp = self._delete(self.lead.id, **self._valid_body(self.lead.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["deleted_lead_id"], self.lead.id)
        self.assertEqual(resp.data["deleted_contact_attempts"], 1)
        self.assertFalse(Lead.objects.filter(pk=self.lead.id).exists())

    def test_related_contact_attempts_deleted(self):
        self.auth(self.superadmin)
        self._delete(self.lead.id, **self._valid_body(self.lead.id))
        self.assertEqual(LeadContactAttempt.objects.filter(lead_id=self.lead.id).count(), 0)

    def test_unrelated_leads_remain(self):
        other = Lead.objects.create(name="Bob", original_phone="0790000002")
        self.auth(self.superadmin)
        self._delete(self.lead.id, **self._valid_body(self.lead.id))
        self.assertTrue(Lead.objects.filter(pk=other.id).exists())

    def test_import_batch_remains(self):
        batch = LeadImportBatch.objects.create(original_filename="x.xlsx")
        self.lead.batch = batch
        self.lead.save(update_fields=["batch"])
        self.auth(self.superadmin)
        self._delete(self.lead.id, **self._valid_body(self.lead.id))
        self.assertTrue(LeadImportBatch.objects.filter(pk=batch.id).exists())

    # -- converted lead protection ---------------------------------------
    def _make_converted_lead(self):
        client = self.make_company()
        pipeline, stages = self.make_pipeline_with_stages()
        deal = self.make_deal(self.superadmin, client, pipeline, stages["lead"])
        lead = Lead.objects.create(
            name="Converted", original_phone="0790000003", status=LeadStatus.CONVERTED,
            converted_client=client, converted_deal=deal, converted_at=timezone.now(),
        )
        return lead, client, deal

    def test_converted_lead_deletion_blocked(self):
        lead, client, deal = self._make_converted_lead()
        self.auth(self.superadmin)
        resp = self._delete(lead.id, **self._valid_body(lead.id))
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "converted_lead")
        self.assertTrue(Lead.objects.filter(pk=lead.id).exists())

    def test_converted_client_and_deal_remain(self):
        lead, client, deal = self._make_converted_lead()
        self.auth(self.superadmin)
        self._delete(lead.id, **self._valid_body(lead.id))
        self.assertTrue(type(client).objects.filter(pk=client.id).exists())
        self.assertTrue(type(deal).objects.filter(pk=deal.id).exists())

    def test_impact_reports_converted_blocked(self):
        lead, _, _ = self._make_converted_lead()
        self.auth(self.superadmin)
        resp = self.client.get(f"/api/leads/{lead.id}/delete-impact/")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["deletion_allowed"])
        self.assertTrue(resp.data["is_converted"])

    # -- audit + integrity ------------------------------------------------
    def test_audit_event_has_no_sensitive_data(self):
        self.lead.notes = "secret notes"
        self.lead.original_phone = "0790000001"
        self.lead.save()
        self.auth(self.superadmin)
        self._delete(self.lead.id, **self._valid_body(self.lead.id))
        event = AuditEvent.objects.filter(action="lead.permanently_deleted").first()
        self.assertIsNotNone(event)
        blob = f"{event.metadata}{event.old_values}{event.new_values}{event.summary}"
        self.assertNotIn("secret notes", blob)
        self.assertNotIn("0790000001", blob)
        self.assertEqual(event.metadata.get("deleted_contact_attempts"), 1)

    def test_second_delete_is_safe(self):
        self.auth(self.superadmin)
        self._delete(self.lead.id, **self._valid_body(self.lead.id))
        resp = self._delete(self.lead.id, **self._valid_body(self.lead.id))
        self.assertEqual(resp.status_code, 404)

    def test_deleted_lead_absent_from_orm(self):
        self.auth(self.superadmin)
        self._delete(self.lead.id, **self._valid_body(self.lead.id))
        self.assertFalse(Lead.objects.filter(pk=self.lead.id).exists())
        self.assertEqual(Lead.objects.filter(name="Alice").count(), 0)
