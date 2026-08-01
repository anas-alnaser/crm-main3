"""Tests for superadmin-only permanent user deletion."""
from crm.apitestbase import APITestBase
from accounts.models import User
from leads.models import Lead


class UserPermanentDeleteTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.superadmin = self.make_superadmin(password="superpass123")
        self.admin = self.make_admin(username="normaladmin")
        self.target = self.make_sales(username="target")

    def _delete(self, url_id, **body):
        return self.client.post(f"/api/users/{url_id}/permanent-delete/", body, format="json")

    def _valid(self, uid):
        return {"current_password": "superpass123", "confirmation": "DELETE USER", "user_id": uid}

    def test_normal_admin_denied(self):
        self.auth(self.admin)
        self.assertEqual(self.client.get(f"/api/users/{self.target.id}/delete-impact/").status_code, 403)
        self.assertEqual(self._delete(self.target.id, **self._valid(self.target.id)).status_code, 403)

    def test_superadmin_cannot_delete_self(self):
        self.auth(self.superadmin)
        resp = self._delete(self.superadmin.id, **self._valid(self.superadmin.id))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "self_delete")
        self.assertTrue(User.objects.filter(pk=self.superadmin.id).exists())

    def test_impact_reports_self_blocked(self):
        self.auth(self.superadmin)
        resp = self.client.get(f"/api/users/{self.superadmin.id}/delete-impact/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["is_self"])
        self.assertFalse(resp.data["deletion_allowed"])

    def test_wrong_password_rejected(self):
        self.auth(self.superadmin)
        resp = self._delete(self.target.id, current_password="nope", confirmation="DELETE USER", user_id=self.target.id)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "incorrect_password")
        self.assertTrue(User.objects.filter(pk=self.target.id).exists())

    def test_superadmin_can_delete_eligible_user(self):
        self.auth(self.superadmin)
        resp = self._delete(self.target.id, **self._valid(self.target.id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["deleted_user_id"], self.target.id)
        self.assertFalse(User.objects.filter(pk=self.target.id).exists())

    def test_ownership_setnull_is_safe(self):
        lead = Lead.objects.create(name="X", original_phone="0790000001", created_by=self.target)
        self.auth(self.superadmin)
        self._delete(self.target.id, **self._valid(self.target.id))
        lead.refresh_from_db()
        self.assertIsNone(lead.created_by_id)  # detached, not deleted

    def test_protected_ownership_blocks_deletion(self):
        company = self.make_company()
        pipeline, stages = self.make_pipeline_with_stages()
        self.make_deal(self.target, company, pipeline, stages["lead"])  # target owns a deal (PROTECT)
        self.auth(self.superadmin)
        resp = self._delete(self.target.id, **self._valid(self.target.id))
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "protected_dependencies")
        self.assertTrue(User.objects.filter(pk=self.target.id).exists())

    def test_valid_superadmin_remains_after_deletion(self):
        other_admin = self.make_superadmin(username="admin2")
        self.auth(self.superadmin)
        self._delete(other_admin.id, **self._valid(other_admin.id))
        # The acting superadmin still exists and is still a superadmin.
        self.superadmin.refresh_from_db()
        self.assertTrue(self.superadmin.is_superuser and self.superadmin.role == "admin")
        self.assertTrue(User.objects.filter(is_active=True, is_superuser=True, role="admin").exists())

    def test_deactivate_reactivate_unchanged(self):
        self.auth(self.superadmin)
        self.assertEqual(self.client.patch(f"/api/users/{self.target.id}/deactivate/").status_code, 200)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertEqual(self.client.patch(f"/api/users/{self.target.id}/reactivate/").status_code, 200)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        # Hard DELETE via the standard route is still disabled.
        self.assertEqual(self.client.delete(f"/api/users/{self.target.id}/").status_code, 405)
