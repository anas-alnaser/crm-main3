"""Tests for the full-reset API (preview + execute)."""
from unittest import mock

from django.contrib.auth import authenticate
from django.core import signing

from accounts.models import User
from clients.models import Client
from crm.test_data_reset import ResetFixtureMixin

PREVIEW_URL = "/api/admin/data-reset/preview/"
EXECUTE_URL = "/api/admin/data-reset/execute/"


class ResetApiTests(ResetFixtureMixin):
    def setUp(self):
        super().setUp()
        self.superadmin = self.make_superadmin(username="owner", password="ownerpass123")
        self.admin = self.make_admin(username="normaladmin")
        self.sales = self.make_sales(username="salesuser")
        self.seed_business_data(owner=self.superadmin)

    def _fresh_token(self):
        self.auth(self.superadmin)
        resp = self.client.get(PREVIEW_URL)
        self.assertEqual(resp.status_code, 200)
        return resp.data["preview_token"]

    def _execute_body(self, token, **overrides):
        body = {
            "current_password": "ownerpass123",
            "confirmation": "DELETE ALL CRM DATA",
            "preserved_user_id": self.superadmin.id,
            "preview_token": token,
        }
        body.update(overrides)
        return body

    # -- authorization ----------------------------------------------------
    def test_anonymous_denied(self):
        self.assertEqual(self.client.get(PREVIEW_URL).status_code, 401)
        self.assertEqual(self.client.post(EXECUTE_URL, {}, format="json").status_code, 401)

    def test_sales_denied(self):
        self.auth(self.sales)
        self.assertEqual(self.client.get(PREVIEW_URL).status_code, 403)
        self.assertEqual(self.client.post(EXECUTE_URL, {}, format="json").status_code, 403)

    def test_normal_admin_denied(self):
        # role=admin + staff but not superuser.
        self.auth(self.admin)
        self.assertEqual(self.client.get(PREVIEW_URL).status_code, 403)
        self.assertEqual(self.client.post(EXECUTE_URL, {}, format="json").status_code, 403)

    # -- preview ----------------------------------------------------------
    def test_preview_works_and_no_writes(self):
        before = (Client.objects.count(), User.objects.count())
        self.auth(self.superadmin)
        resp = self.client.get(PREVIEW_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("preview_token", resp.data)
        self.assertIn("counts", resp.data)
        self.assertEqual(resp.data["other_users_to_delete"], 4)
        # The internal snapshot fingerprint is not exposed.
        self.assertNotIn("snapshot", resp.data)
        self.assertEqual((Client.objects.count(), User.objects.count()), before)

    # -- execute gating ---------------------------------------------------
    def test_wrong_password_denied(self):
        token = self._fresh_token()
        resp = self.client.post(EXECUTE_URL, self._execute_body(token, current_password="nope"), format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "incorrect_password")
        self.assertTrue(Client.objects.exists())

    def test_wrong_phrase_denied(self):
        token = self._fresh_token()
        resp = self.client.post(EXECUTE_URL, self._execute_body(token, confirmation="delete all"), format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "confirmation_mismatch")

    def test_missing_preview_token_denied(self):
        self.auth(self.superadmin)
        resp = self.client.post(EXECUTE_URL, self._execute_body(""), format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "preview_required")

    def test_expired_preview_token_denied(self):
        token = self._fresh_token()
        with mock.patch("crm.reset_views.signing.loads", side_effect=signing.SignatureExpired("old")):
            resp = self.client.post(EXECUTE_URL, self._execute_body(token), format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "preview_expired")
        self.assertTrue(Client.objects.exists())

    def test_mismatching_preserved_user_id_denied(self):
        token = self._fresh_token()
        resp = self.client.post(EXECUTE_URL, self._execute_body(token, preserved_user_id=self.superadmin.id + 999), format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "preserved_user_mismatch")

    def test_single_use_preview_token(self):
        token = self._fresh_token()
        first = self.client.post(EXECUTE_URL, self._execute_body(token), format="json")
        self.assertEqual(first.status_code, 200)
        second = self.client.post(EXECUTE_URL, self._execute_body(token), format="json")
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.data["code"], "preview_used")

    # -- successful execution --------------------------------------------
    def test_valid_reset_succeeds(self):
        token = self._fresh_token()
        resp = self.client.post(EXECUTE_URL, self._execute_body(token), format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("CRM data reset completed", resp.data["detail"])
        self.assertEqual(User.objects.count(), 1)
        self.assertFalse(Client.objects.exists())
        # Safe counts only.
        for value in resp.data["deleted"].values():
            self.assertIsInstance(value, int)

    def test_preserved_user_still_authenticated_after_reset(self):
        token = self._fresh_token()
        self.client.post(EXECUTE_URL, self._execute_body(token), format="json")
        self.assertIsNotNone(authenticate(username="owner", password="ownerpass123"))
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.data["is_superuser"])

    def test_endpoint_is_rate_limited(self):
        self.auth(self.superadmin)
        statuses = set()
        for _ in range(60):
            statuses.add(self.client.get(PREVIEW_URL).status_code)
            if 429 in statuses:
                break
        self.assertIn(429, statuses)
