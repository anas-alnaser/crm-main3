from crm.apitestbase import APITestBase
from accounts.models import User


class AuthFlowTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin(password="adminpass123")

    def test_login_returns_tokens(self):
        resp = self.client.post("/api/auth/token/", {"username": "admin", "password": "adminpass123"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_login_wrong_password_rejected(self):
        resp = self.client.post("/api/auth/token/", {"username": "admin", "password": "nope"}, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_me_requires_auth(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_me_returns_current_user(self):
        tokens = self.client.post("/api/auth/token/", {"username": "admin", "password": "adminpass123"}, format="json").data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["username"], "admin")
        self.assertEqual(resp.data["role"], "admin")

    def test_refresh_returns_new_access(self):
        tokens = self.client.post("/api/auth/token/", {"username": "admin", "password": "adminpass123"}, format="json").data
        resp = self.client.post("/api/auth/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)


class UserAdminTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.sales = self.make_sales()

    def test_sales_cannot_access_users(self):
        self.auth(self.sales)
        self.assertEqual(self.client.get("/api/users/").status_code, 403)

    def test_admin_creates_user(self):
        self.auth(self.admin)
        resp = self.client.post("/api/users/", {"username": "newrep", "role": "sales", "temp_password": "temppass123"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertNotIn("temp_password", resp.data)
        self.assertTrue(User.objects.filter(username="newrep").exists())

    def test_duplicate_email_rejected(self):
        self.auth(self.admin)
        self.client.post("/api/users/", {"username": "a", "role": "sales", "temp_password": "temppass123", "email": "dup@example.com"}, format="json")
        resp = self.client.post("/api/users/", {"username": "b", "role": "sales", "temp_password": "temppass123", "email": "DUP@example.com"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_hard_delete_disabled(self):
        self.auth(self.admin)
        resp = self.client.delete(f"/api/users/{self.sales.id}/")
        self.assertEqual(resp.status_code, 405)
        self.assertTrue(User.objects.filter(id=self.sales.id).exists())

    def test_deactivate_and_reactivate(self):
        self.auth(self.admin)
        self.client.patch(f"/api/users/{self.sales.id}/deactivate/")
        self.sales.refresh_from_db()
        self.assertFalse(self.sales.is_active)
        self.client.patch(f"/api/users/{self.sales.id}/reactivate/")
        self.sales.refresh_from_db()
        self.assertTrue(self.sales.is_active)

    def test_cannot_self_deactivate(self):
        self.auth(self.admin)
        resp = self.client.patch(f"/api/users/{self.admin.id}/deactivate/")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["code"], "self_deactivate")

    def test_cannot_demote_last_admin(self):
        # Only one admin in the system demoting itself must be blocked.
        User.objects.exclude(pk=self.admin.pk).filter(role=User.Role.ADMIN).delete()
        self.auth(self.admin)
        resp = self.client.patch(f"/api/users/{self.admin.id}/", {"role": "sales"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_can_demote_admin_when_another_exists(self):
        other = self.make_admin(username="admin2")
        self.auth(self.admin)
        resp = self.client.patch(f"/api/users/{other.id}/", {"role": "sales"}, format="json")
        self.assertEqual(resp.status_code, 200)
        other.refresh_from_db()
        self.assertEqual(other.role, "sales")
        self.assertFalse(other.is_staff)

    def test_password_reset_changes_password(self):
        self.auth(self.admin)
        resp = self.client.post(f"/api/users/{self.sales.id}/reset-password/", {"temp_password": "brandnew123"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("temp_password", resp.data)
        self.sales.refresh_from_db()
        self.assertTrue(self.sales.check_password("brandnew123"))
