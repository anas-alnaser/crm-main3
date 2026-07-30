from crm.apitestbase import APITestBase
from tasks.models import Task


class TaskOwnershipTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.owner = self.make_sales(username="owner")
        self.other = self.make_sales(username="other")
        self.task = Task.objects.create(title="Owned task", created_by=self.owner)

    def test_create_sets_creator(self):
        self.auth(self.other)
        resp = self.client.post("/api/tasks/", {"title": "New task", "status": "todo"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Task.objects.get(title="New task").created_by_id, self.other.id)

    def test_all_can_read(self):
        self.auth(self.other)
        self.assertEqual(self.client.get("/api/tasks/").status_code, 200)

    def test_owner_can_update_and_delete(self):
        self.auth(self.owner)
        self.assertEqual(self.client.patch(f"/api/tasks/{self.task.id}/", {"status": "doing"}, format="json").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/tasks/{self.task.id}/").status_code, 204)

    def test_non_owner_cannot_update_or_delete(self):
        self.auth(self.other)
        self.assertEqual(self.client.patch(f"/api/tasks/{self.task.id}/", {"status": "doing"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/tasks/{self.task.id}/").status_code, 403)

    def test_admin_can_update_any(self):
        self.auth(self.admin)
        self.assertEqual(self.client.patch(f"/api/tasks/{self.task.id}/", {"status": "done"}, format="json").status_code, 200)
