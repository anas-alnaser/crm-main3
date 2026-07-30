from datetime import timedelta

from django.utils import timezone

from crm.apitestbase import APITestBase
from meetings.models import Meeting


def meeting_payload(**kwargs):
    start = timezone.now() + timedelta(days=1)
    data = {
        "title": "Discovery",
        "start_datetime": start.isoformat(),
        "end_datetime": (start + timedelta(hours=1)).isoformat(),
        "status": "scheduled",
    }
    data.update(kwargs)
    return data


class MeetingScopeTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.rep_a = self.make_sales(username="rep_a")
        self.rep_b = self.make_sales(username="rep_b")
        self.meeting_a = Meeting.objects.create(
            title="A meeting",
            start_datetime=timezone.now() + timedelta(days=1),
            end_datetime=timezone.now() + timedelta(days=1, hours=1),
            owner=self.rep_a,
        )

    def test_create_sets_owner_for_sales(self):
        self.auth(self.rep_b)
        resp = self.client.post("/api/meetings/", meeting_payload(title="B meeting"), format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Meeting.objects.get(title="B meeting").owner_id, self.rep_b.id)

    def test_sales_only_sees_own(self):
        self.auth(self.rep_b)
        ids = [m["id"] for m in self.client.get("/api/meetings/").data["results"]]
        self.assertNotIn(self.meeting_a.id, ids)

    def test_sales_cannot_read_others_detail(self):
        self.auth(self.rep_b)
        self.assertEqual(self.client.get(f"/api/meetings/{self.meeting_a.id}/").status_code, 404)

    def test_admin_sees_all_with_scope(self):
        self.auth(self.admin)
        ids = [m["id"] for m in self.client.get("/api/meetings/?scope=all").data["results"]]
        self.assertIn(self.meeting_a.id, ids)

    def test_upcoming_returns_scheduled(self):
        self.auth(self.rep_a)
        resp = self.client.get("/api/meetings/upcoming/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(m["id"] == self.meeting_a.id for m in resp.data))
