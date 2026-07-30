from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from crm.apitestbase import APITestBase
from sales.models import Deal, SalesSettings, Stage


class DealPermissionTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.owner = self.make_sales(username="owner")
        self.other = self.make_sales(username="other")
        self.pipeline, self.stages = self.make_pipeline_with_stages()
        self.company = self.make_company()
        self.deal = self.make_deal(self.owner, self.company, self.pipeline, self.stages["lead"], value="1000.00")

    def test_value_masked_for_non_owner_sales(self):
        self.auth(self.other)
        row = next(d for d in self.client.get("/api/deals/").data["results"] if d["id"] == self.deal.id)
        self.assertIsNone(row["value"])
        self.assertIsNone(row["commission"])

    def test_owner_sees_value(self):
        self.auth(self.owner)
        row = next(d for d in self.client.get("/api/deals/").data["results"] if d["id"] == self.deal.id)
        self.assertEqual(row["value"], "1000.00")

    def test_sales_create_forces_self_owner(self):
        self.auth(self.other)
        resp = self.client.post(
            "/api/deals/",
            {"title": "Mine", "company": self.company.id, "pipeline": self.pipeline.id, "stage": self.stages["lead"].id, "currency": "JOD", "owner": self.owner.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(Deal.objects.get(title="Mine").owner_id, self.other.id)

    def test_sales_cannot_reassign_owner_on_update(self):
        self.auth(self.owner)
        resp = self.client.patch(f"/api/deals/{self.deal.id}/", {"owner": self.other.id}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.owner_id, self.owner.id)

    def test_admin_can_reassign_owner(self):
        self.auth(self.admin)
        resp = self.client.patch(f"/api/deals/{self.deal.id}/", {"owner": self.other.id}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.owner_id, self.other.id)

    def test_non_owner_cannot_modify(self):
        self.auth(self.other)
        self.assertEqual(self.client.patch(f"/api/deals/{self.deal.id}/", {"title": "x"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/deals/{self.deal.id}/").status_code, 403)

    def test_sales_cannot_move_others_deal(self):
        self.auth(self.other)
        resp = self.client.patch(f"/api/deals/{self.deal.id}/move/", {"stage": self.stages["won"].id}, format="json")
        self.assertEqual(resp.status_code, 403)


class DealLifecycleTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.pipeline, self.stages = self.make_pipeline_with_stages()
        self.company = self.make_company()
        self.deal = self.make_deal(self.admin, self.company, self.pipeline, self.stages["lead"], value="1000.00")

    def test_won_transition_sets_status_and_closed_at(self):
        self.auth(self.admin)
        self.client.patch(f"/api/deals/{self.deal.id}/move/", {"stage": self.stages["won"].id}, format="json")
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.status, "won")
        self.assertIsNotNone(self.deal.closed_at)

    def test_lost_transition_sets_closed_at(self):
        self.deal.stage = self.stages["lost"]
        self.deal.save()
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.status, "lost")
        self.assertIsNotNone(self.deal.closed_at)

    def test_reopening_clears_closed_at(self):
        self.deal.stage = self.stages["won"]
        self.deal.save()
        self.deal.stage = self.stages["lead"]
        self.deal.save()
        self.deal.refresh_from_db()
        self.assertEqual(self.deal.status, "open")
        self.assertIsNone(self.deal.closed_at)


class SalesMetricsTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.rep = self.make_sales(username="rep")
        self.pipeline, self.stages = self.make_pipeline_with_stages()
        self.company = self.make_company()
        SalesSettings.objects.update_or_create(pk=1, defaults={"commission_rate_percent": Decimal("10")})

    def _won_deal(self, owner, value, closed_at=None):
        deal = self.make_deal(owner, self.company, self.pipeline, self.stages["won"], value=value)
        if closed_at:
            Deal.objects.filter(pk=deal.pk).update(closed_at=closed_at)
        return deal

    def test_commission_uses_rate(self):
        self._won_deal(self.rep, "1000.00")
        self.make_deal(self.rep, self.company, self.pipeline, self.stages["lead"], value="500.00")
        self.auth(self.rep)
        data = self.client.get("/api/commission/").data
        self.assertEqual(Decimal(data["earned_commission"]), Decimal("100.00"))  # 10% of 1000
        self.assertEqual(Decimal(data["potential_commission"]), Decimal("50.00"))  # 10% of 500

    def test_leaderboard_month_uses_closed_at(self):
        # A deal closed last month should not count for this_month.
        last_month = timezone.now() - timedelta(days=40)
        self._won_deal(self.rep, "1000.00", closed_at=last_month)
        self.auth(self.admin)
        row = next(r for r in self.client.get("/api/leaderboard/?period=this_month").data["results"] if r.get("rep_id") == self.rep.id)
        self.assertEqual(row["won_count"], 0)
        row_all = next(r for r in self.client.get("/api/leaderboard/?period=all_time").data["results"] if r.get("rep_id") == self.rep.id)
        self.assertEqual(row_all["won_count"], 1)

    def test_leaderboard_masks_other_reps_for_sales(self):
        self._won_deal(self.rep, "1000.00")
        viewer = self.make_sales(username="viewer")
        self.auth(viewer)
        rows = self.client.get("/api/leaderboard/").data["results"]
        other_rows = [r for r in rows if not r["is_current_user"]]
        self.assertTrue(other_rows)
        for row in other_rows:
            # Money figures for other reps must be hidden from a sales viewer.
            self.assertNotIn("earned_commission", row)
            self.assertNotIn("won_value", row)

    def test_dashboard_won_this_month_uses_closed_at(self):
        last_month = timezone.now() - timedelta(days=40)
        self._won_deal(self.admin, "1000.00", closed_at=last_month)
        self._won_deal(self.admin, "2000.00")  # closed now
        self.auth(self.admin)
        data = self.client.get("/api/dashboard/stats/").data
        self.assertEqual(data["deals_won_this_month"], 1)


class PipelineStageDeleteTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.pipeline, self.stages = self.make_pipeline_with_stages()
        self.company = self.make_company()

    def test_stage_with_deals_is_protected(self):
        self.make_deal(self.admin, self.company, self.pipeline, self.stages["lead"])
        self.auth(self.admin)
        resp = self.client.delete(f"/api/stages/{self.stages['lead'].id}/")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.data["code"], "protected")

    def test_pipeline_with_deals_is_protected(self):
        self.make_deal(self.admin, self.company, self.pipeline, self.stages["lead"])
        self.auth(self.admin)
        resp = self.client.delete(f"/api/pipelines/{self.pipeline.id}/")
        self.assertEqual(resp.status_code, 409)

    def test_empty_stage_can_be_deleted(self):
        empty = Stage.objects.create(pipeline=self.pipeline, name="Empty", order=9)
        self.auth(self.admin)
        self.assertEqual(self.client.delete(f"/api/stages/{empty.id}/").status_code, 204)
