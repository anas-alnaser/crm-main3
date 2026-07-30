from crm.apitestbase import APITestBase
from activities.models import Activity


class ActivityOwnershipTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.owner = self.make_sales(username="owner")
        self.other = self.make_sales(username="other")
        self.activity = Activity.objects.create(type="note", content="Owned", created_by=self.owner)

    def test_create_sets_creator(self):
        self.auth(self.other)
        resp = self.client.post("/api/activities/", {"type": "note", "content": "Hi"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Activity.objects.get(content="Hi").created_by_id, self.other.id)

    def test_non_owner_cannot_modify(self):
        self.auth(self.other)
        self.assertEqual(self.client.patch(f"/api/activities/{self.activity.id}/", {"content": "x"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/activities/{self.activity.id}/").status_code, 403)

    def test_owner_can_modify(self):
        self.auth(self.owner)
        self.assertEqual(self.client.patch(f"/api/activities/{self.activity.id}/", {"content": "x"}, format="json").status_code, 200)
