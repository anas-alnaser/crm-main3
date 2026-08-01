"""Tests for superadmin-only permanent company (client) deletion."""
from crm.apitestbase import APITestBase
from clients.models import Client
from projects.models import Project
from sales.models import Deal


class CompanyPermanentDeleteTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.superadmin = self.make_superadmin(password="superpass123")
        self.admin = self.make_admin(username="normaladmin")
        self.company = self.make_company(name="Acme")
        self.pipeline, self.stages = self.make_pipeline_with_stages()

    def _delete(self, url_id, **body):
        return self.client.post(f"/api/clients/{url_id}/permanent-delete/", body, format="json")

    def _valid(self, cid, **extra):
        return {"current_password": "superpass123", "confirmation": "DELETE COMPANY", "client_id": cid, **extra}

    def test_normal_admin_denied(self):
        self.auth(self.admin)
        self.assertEqual(self.client.get(f"/api/clients/{self.company.id}/delete-impact/").status_code, 403)
        self.assertEqual(self._delete(self.company.id, **self._valid(self.company.id)).status_code, 403)

    def test_superadmin_impact_counts(self):
        self.make_deal(self.superadmin, self.company, self.pipeline, self.stages["lead"])
        Project.objects.create(title="Site", client=self.company)
        self.auth(self.superadmin)
        resp = self.client.get(f"/api/clients/{self.company.id}/delete-impact/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["impact"]["deals"], 1)
        self.assertEqual(resp.data["impact"]["projects"], 1)
        self.assertTrue(resp.data["dependencies_exist"])
        # Read-only.
        self.assertTrue(Client.objects.filter(pk=self.company.id).exists())
        self.assertEqual(Deal.objects.count(), 1)

    def test_missing_cascade_confirmation_rejected(self):
        self.make_deal(self.superadmin, self.company, self.pipeline, self.stages["lead"])
        self.auth(self.superadmin)
        resp = self._delete(self.company.id, **self._valid(self.company.id))  # no cascade_confirmed
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "cascade_confirmation_required")
        self.assertTrue(Client.objects.filter(pk=self.company.id).exists())

    def test_transactional_cascade_delete(self):
        deal = self.make_deal(self.superadmin, self.company, self.pipeline, self.stages["lead"])
        project = Project.objects.create(title="Site", client=self.company)
        self.auth(self.superadmin)
        resp = self._delete(self.company.id, **self._valid(self.company.id, cascade_confirmed=True))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Client.objects.filter(pk=self.company.id).exists())
        self.assertFalse(Deal.objects.filter(pk=deal.id).exists())
        self.assertFalse(Project.objects.filter(pk=project.id).exists())

    def test_no_dependencies_deletes_without_cascade_flag(self):
        self.auth(self.superadmin)
        resp = self._delete(self.company.id, **self._valid(self.company.id))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Client.objects.filter(pk=self.company.id).exists())

    def test_unrelated_companies_remain(self):
        other = self.make_company(name="Other")
        self.auth(self.superadmin)
        self._delete(self.company.id, **self._valid(self.company.id))
        self.assertTrue(Client.objects.filter(pk=other.id).exists())

    def test_wrong_password_rejected(self):
        self.auth(self.superadmin)
        resp = self._delete(self.company.id, current_password="nope", confirmation="DELETE COMPANY", client_id=self.company.id)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "incorrect_password")

    def test_archive_restore_unchanged(self):
        # Archive/restore still work and hard DELETE is still 405.
        self.auth(self.admin)
        self.assertEqual(self.client.patch(f"/api/clients/{self.company.id}/archive/").status_code, 200)
        self.company.refresh_from_db()
        self.assertTrue(self.company.is_archived)
        self.assertEqual(self.client.patch(f"/api/clients/{self.company.id}/restore/").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/clients/{self.company.id}/").status_code, 405)
