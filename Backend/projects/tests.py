from crm.apitestbase import APITestBase
from clients.models import Client
from projects.models import Project


class ProjectOwnershipTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.owner = self.make_sales(username="owner")
        self.other = self.make_sales(username="other")
        self.company = Client.objects.create(name="Co", created_by=self.owner)
        self.project = Project.objects.create(title="Owned", client=self.company, created_by=self.owner)

    def test_create_sets_creator(self):
        self.auth(self.other)
        resp = self.client.post(
            "/api/projects/",
            {"title": "New", "client": self.company.id, "type": "web", "status": "lead"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Project.objects.get(title="New").created_by_id, self.other.id)

    def test_non_owner_cannot_modify(self):
        self.auth(self.other)
        self.assertEqual(self.client.patch(f"/api/projects/{self.project.id}/", {"status": "paid"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/projects/{self.project.id}/").status_code, 403)

    def test_owner_can_modify(self):
        self.auth(self.owner)
        self.assertEqual(self.client.patch(f"/api/projects/{self.project.id}/", {"status": "paid"}, format="json").status_code, 200)
