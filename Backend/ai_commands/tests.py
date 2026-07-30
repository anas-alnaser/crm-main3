from unittest.mock import patch

from django.utils import timezone
from datetime import timedelta
from rest_framework import status

from crm.apitestbase import APITestBase
from crm.throttling import AICommandThrottle
from ai_commands.models import AICommandConfirmation, AICommandLog
from ai_commands.services import AICommandError
from clients.models import Client
from sales.models import Deal


def draft(intent, fields=None, confidence=0.95, missing=None):
    return {"intent": intent, "fields": fields or {}, "confidence": confidence, "missing": missing or []}


class AICommandBase(APITestBase):
    def setUp(self):
        super().setUp()
        self.admin = self.make_admin()
        self.sales = self.make_sales()
        self.pipeline, self.stages = self.make_pipeline_with_stages()
        self.company = self.make_company("Acme")
        self.deal = self.make_deal(self.admin, self.company, self.pipeline, self.stages["lead"], title="Bridge deal", value="1000.00")

    def run_command(self, command_draft, user=None):
        self.auth(user or self.admin)
        with patch("ai_commands.views.interpret_command", return_value=command_draft):
            return self.client.post("/api/ai/command/", {"text": "do something"}, format="json")

    def confirm(self, confirmation_id, user=None, extra=None):
        self.auth(user or self.admin)
        body = {"confirmation_id": confirmation_id}
        if extra:
            body.update(extra)
        return self.client.post("/api/ai/command/confirm/", body, format="json")


class Tier1Tests(AICommandBase):
    def test_tier1_executes_once(self):
        resp = self.run_command(draft("create_company", {"company_name": "NewCo"}))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["acted"])
        self.assertIn("action_id", resp.data)
        self.assertEqual(Client.objects.filter(name="NewCo").count(), 1)
        log = AICommandLog.objects.get(id=resp.data["action_id"])
        self.assertEqual(log.outcome, AICommandLog.Outcome.EXECUTED)

    def test_low_confidence_does_not_mutate(self):
        resp = self.run_command(draft("create_company", {"company_name": "NewCo"}, confidence=0.4))
        self.assertFalse(resp.data["acted"])
        self.assertTrue(resp.data["needs_review"])
        self.assertFalse(Client.objects.filter(name="NewCo").exists())

    def test_missing_fields_do_not_mutate(self):
        before = Deal.objects.count()
        resp = self.run_command(draft("create_deal", {"title": "X"}))  # no company/stage
        self.assertFalse(resp.data["acted"])
        self.assertTrue(resp.data["needs_review"] or resp.data["requires_disambiguation"])
        self.assertEqual(Deal.objects.count(), before)

    def test_ambiguous_records_do_not_mutate(self):
        # Two companies match "Widget" by substring with no exact match -> ambiguous.
        self.make_company("Widget East")
        self.make_company("Widget West")
        before = Deal.objects.count()
        resp = self.run_command(draft("create_deal", {"title": "X", "company_name": "Widget", "target_stage": "Negotiation"}))
        self.assertFalse(resp.data["acted"])
        self.assertTrue(resp.data["requires_disambiguation"])
        self.assertIn("company_name", resp.data["options"])
        self.assertEqual(Deal.objects.count(), before)


class Tier2ConfirmationTests(AICommandBase):
    def preview_value_change(self):
        return self.run_command(draft("update_deal_value", {"deal_identifier": "Bridge deal", "value": "5000"}))

    def test_tier2_does_not_execute_initially(self):
        resp = self.preview_value_change()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["acted"])
        self.assertTrue(resp.data["requires_confirmation"])
        self.assertIn("confirmation_id", resp.data)
        self.deal.refresh_from_db()
        self.assertEqual(str(self.deal.value), "1000.00")

    def test_preview_contains_old_and_new(self):
        resp = self.preview_value_change()
        preview = resp.data["preview"]
        self.assertEqual(preview["old"], "1000.00")
        self.assertEqual(preview["new"], "5000")

    def test_valid_confirmation_executes_once(self):
        resp = self.preview_value_change()
        cid = resp.data["confirmation_id"]
        confirmed = self.confirm(cid)
        self.assertEqual(confirmed.status_code, 200)
        self.assertTrue(confirmed.data["acted"])
        self.assertIn("action_id", confirmed.data)
        self.deal.refresh_from_db()
        self.assertEqual(str(self.deal.value), "5000.00")
        log = AICommandLog.objects.get(id=confirmed.data["action_id"])
        self.assertEqual(log.outcome, AICommandLog.Outcome.CONFIRMED)

    def test_reusing_confirmation_is_rejected(self):
        cid = self.preview_value_change().data["confirmation_id"]
        self.confirm(cid)
        second = self.confirm(cid)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(second.data["code"], "already_used")

    def test_confirmation_not_usable_by_another_user(self):
        cid = self.preview_value_change().data["confirmation_id"]
        other = self.make_admin(username="admin2")
        resp = self.confirm(cid, user=other)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.deal.refresh_from_db()
        self.assertEqual(str(self.deal.value), "1000.00")

    def test_expired_confirmation_is_rejected(self):
        cid = self.preview_value_change().data["confirmation_id"]
        AICommandConfirmation.objects.filter(id=cid).update(expires_at=timezone.now() - timedelta(seconds=1))
        resp = self.confirm(cid)
        self.assertEqual(resp.status_code, status.HTTP_410_GONE)
        self.deal.refresh_from_db()
        self.assertEqual(str(self.deal.value), "1000.00")

    def test_unknown_confirmation_is_rejected(self):
        resp = self.confirm("00000000-0000-0000-0000-000000000000")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_browser_modified_fields_are_ignored(self):
        cid = self.preview_value_change().data["confirmation_id"]
        # Attempt to smuggle a different value through the confirm request body.
        confirmed = self.confirm(cid, extra={"draft": {"intent": "update_deal_value", "fields": {"deal_identifier": "Bridge deal", "value": "999999"}}, "value": "999999"})
        self.assertEqual(confirmed.status_code, 200)
        self.deal.refresh_from_db()
        self.assertEqual(str(self.deal.value), "5000.00")  # stored draft won, not 999999

    def test_cancelled_confirmation_cannot_execute(self):
        cid = self.preview_value_change().data["confirmation_id"]
        self.auth(self.admin)
        cancel = self.client.post("/api/ai/command/cancel/", {"confirmation_id": cid}, format="json")
        self.assertEqual(cancel.status_code, 200)
        resp = self.confirm(cid)
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data["code"], "cancelled")


class BlockedAndUnknownTests(AICommandBase):
    def test_blocked_command_no_mutation(self):
        resp = self.run_command(draft("delete_deal", {"deal_identifier": "Bridge deal"}))
        self.assertTrue(resp.data["blocked"])
        self.assertIn("refusal", resp.data)
        self.assertTrue(Deal.objects.filter(id=self.deal.id).exists())
        self.assertTrue(AICommandLog.objects.filter(outcome=AICommandLog.Outcome.BLOCKED).exists())

    def test_unknown_command_no_mutation(self):
        resp = self.run_command(draft("teleport_deal", {}))
        self.assertTrue(resp.data["blocked"])
        self.assertFalse(resp.data["acted"])


class UndoTests(AICommandBase):
    def test_undo_removes_created_record(self):
        resp = self.run_command(draft("create_company", {"company_name": "Undoable Co"}))
        action_id = resp.data["action_id"]
        self.assertTrue(Client.objects.filter(name="Undoable Co").exists())
        self.auth(self.admin)
        undo = self.client.post("/api/ai/command/undo/", {"action_id": action_id}, format="json")
        self.assertEqual(undo.status_code, 200)
        self.assertFalse(Client.objects.filter(name="Undoable Co").exists())

    def test_undo_restores_update(self):
        cid = self.run_command(draft("update_deal_value", {"deal_identifier": "Bridge deal", "value": "7000"})).data["confirmation_id"]
        action_id = self.confirm(cid).data["action_id"]
        self.auth(self.admin)
        self.client.post("/api/ai/command/undo/", {"action_id": action_id}, format="json")
        self.deal.refresh_from_db()
        self.assertEqual(str(self.deal.value), "1000.00")

    def test_undo_cannot_run_twice(self):
        action_id = self.run_command(draft("create_company", {"company_name": "Twice Co"})).data["action_id"]
        self.auth(self.admin)
        self.client.post("/api/ai/command/undo/", {"action_id": action_id}, format="json")
        second = self.client.post("/api/ai/command/undo/", {"action_id": action_id}, format="json")
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.data["code"], "already_undone")

    def test_user_cannot_undo_another_users_action(self):
        action_id = self.run_command(draft("create_company", {"company_name": "Foreign Co"})).data["action_id"]
        other = self.make_admin(username="admin3")
        self.auth(other)
        resp = self.client.post("/api/ai/command/undo/", {"action_id": action_id}, format="json")
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Client.objects.filter(name="Foreign Co").exists())


class AISecurityTests(AICommandBase):
    def test_sales_user_rejected(self):
        resp = self.run_command(draft("create_company", {"company_name": "NoCo"}), user=self.sales)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Client.objects.filter(name="NoCo").exists())

    def test_confirm_endpoint_rejects_sales(self):
        self.auth(self.sales)
        resp = self.client.post("/api/ai/command/confirm/", {"confirmation_id": "00000000-0000-0000-0000-000000000000"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_provider_error_does_not_leak_details(self):
        self.auth(self.admin)
        with patch("ai_commands.views.interpret_command", side_effect=AICommandError("SENSITIVE provider stack trace")):
            resp = self.client.post("/api/ai/command/", {"text": "hi"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertNotIn("SENSITIVE", str(resp.data))
        self.assertEqual(resp.data["code"], "provider_error")

    def test_throttling_applies(self):
        self.auth(self.admin)
        with patch.object(AICommandThrottle, "get_rate", return_value="2/min"):
            with patch("ai_commands.views.interpret_command", return_value=draft("teleport_deal", {})):
                r1 = self.client.post("/api/ai/command/", {"text": "a"}, format="json")
                r2 = self.client.post("/api/ai/command/", {"text": "b"}, format="json")
                r3 = self.client.post("/api/ai/command/", {"text": "c"}, format="json")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r3.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_command_length_limit(self):
        self.auth(self.admin)
        with patch("ai_commands.views.interpret_command", return_value=draft("teleport_deal", {})):
            resp = self.client.post("/api/ai/command/", {"text": "x" * 5000}, format="json")
        self.assertEqual(resp.status_code, 400)
