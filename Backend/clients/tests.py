from crm.apitestbase import APITestBase
from clients.models import Client


class ClientPermissionTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.owner = self.make_sales(username="owner")
        self.other = self.make_sales(username="other")
        self.client_obj = Client.objects.create(name="Owned Co", created_by=self.owner)

    def test_anonymous_denied(self):
        self.assertEqual(self.client.get("/api/clients/").status_code, 401)

    def test_all_authenticated_can_read(self):
        for user in (self.admin, self.owner, self.other):
            self.auth(user)
            self.assertEqual(self.client.get("/api/clients/").status_code, 200)

    def test_sales_create_sets_created_by(self):
        self.auth(self.other)
        resp = self.client.post("/api/clients/", {"name": "Fresh Co", "status": "active"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Client.objects.get(name="Fresh Co").created_by_id, self.other.id)

    def test_created_by_cannot_be_mass_assigned(self):
        self.auth(self.other)
        resp = self.client.post("/api/clients/", {"name": "Spoof Co", "status": "active", "created_by": self.admin.id}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Client.objects.get(name="Spoof Co").created_by_id, self.other.id)

    def test_owner_can_update(self):
        self.auth(self.owner)
        resp = self.client.patch(f"/api/clients/{self.client_obj.id}/", {"country": "Jordan"}, format="json")
        self.assertEqual(resp.status_code, 200)

    def test_non_owner_sales_cannot_update(self):
        self.auth(self.other)
        resp = self.client.patch(f"/api/clients/{self.client_obj.id}/", {"country": "Jordan"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_update_any(self):
        self.auth(self.admin)
        resp = self.client.patch(f"/api/clients/{self.client_obj.id}/", {"country": "Jordan"}, format="json")
        self.assertEqual(resp.status_code, 200)

    def test_delete_disabled_for_everyone(self):
        for user in (self.owner, self.admin):
            self.auth(user)
            resp = self.client.delete(f"/api/clients/{self.client_obj.id}/")
            self.assertEqual(resp.status_code, 405)
        self.assertTrue(Client.objects.filter(id=self.client_obj.id).exists())


class ClientArchiveTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.sales = self.make_sales()
        self.company = Client.objects.create(name="Archivable", created_by=self.admin)

    def test_admin_can_archive_and_restore(self):
        self.auth(self.admin)
        resp = self.client.patch(f"/api/clients/{self.company.id}/archive/")
        self.assertEqual(resp.status_code, 200)
        self.company.refresh_from_db()
        self.assertTrue(self.company.is_archived)
        self.assertIsNotNone(self.company.archived_at)

        resp = self.client.patch(f"/api/clients/{self.company.id}/restore/")
        self.assertEqual(resp.status_code, 200)
        self.company.refresh_from_db()
        self.assertFalse(self.company.is_archived)

    def test_sales_cannot_archive(self):
        self.auth(self.sales)
        resp = self.client.patch(f"/api/clients/{self.company.id}/archive/")
        self.assertEqual(resp.status_code, 403)

    def test_archived_excluded_from_default_list(self):
        self.company.is_archived = True
        self.company.save(update_fields=["is_archived"])
        self.auth(self.admin)
        default_ids = [row["id"] for row in self.client.get("/api/clients/").data["results"]]
        self.assertNotIn(self.company.id, default_ids)
        archived_ids = [row["id"] for row in self.client.get("/api/clients/?archived=true").data["results"]]
        self.assertIn(self.company.id, archived_ids)

    def test_archiving_preserves_deals(self):
        pipeline, stages = self.make_pipeline_with_stages()
        deal = self.make_deal(self.admin, self.company, pipeline, stages["lead"])
        self.auth(self.admin)
        self.client.patch(f"/api/clients/{self.company.id}/archive/")
        from sales.models import Deal

        self.assertTrue(Deal.objects.filter(id=deal.id).exists())
