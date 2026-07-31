"""Tests for the internal scheduler reconciliation endpoint.

Covers, per requirement:
  * unauthenticated rejection (no token; and a browser/admin session)
  * invalid-token rejection (malformed JWT, wrong service account, unverified
    email, untrusted issuer)
  * successful scheduler execution
  * idempotency
  * inactivity closure
  * 9:00 PM closure

The Google OIDC signature check (``verify_oidc_token``) is patched so the suite
never touches the network; the identity enforcement and the reconciliation
service run for real. Time is pinned via ``workforce.services.timezone.now`` so
the closure maths is deterministic.
"""
from datetime import date, time
from unittest import mock

from django.test import override_settings
from django.urls import reverse

from crm.apitestbase import APITestBase
from workforce.models import ClosingReason, WorkSession
from workforce.timezones import combine_local

# A known Sunday (a working day) in Asia/Amman.
SUNDAY = date(2026, 8, 2)
SA_EMAIL = "crm-scheduler@example-project.iam.gserviceaccount.com"
AUDIENCE = "https://crm-api.example.run.app/internal/workforce/reconcile/"


def amman(day, hour, minute=0):
    """UTC instant for a given Amman wall-clock time."""
    return combine_local(day, time(hour, minute), "Asia/Amman")


def valid_claims(**overrides):
    claims = {
        "iss": "https://accounts.google.com",
        "aud": AUDIENCE,
        "email": SA_EMAIL,
        "email_verified": True,
        "sub": "1234567890",
        "exp": 9999999999,
        "iat": 1111111111,
    }
    claims.update(overrides)
    return claims


@override_settings(
    WORKFORCE_SCHEDULER_AUDIENCE=AUDIENCE,
    WORKFORCE_SCHEDULER_SERVICE_ACCOUNT=SA_EMAIL,
)
class SchedulerAuthTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("workforce_reconcile")

    def test_missing_token_rejected(self):
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data["code"], "missing_token")

    def test_authenticated_browser_user_cannot_invoke(self):
        # An admin logged into the SPA/admin has no scheduler OIDC bearer token,
        # so they are rejected exactly like an anonymous caller.
        self.auth(self.make_admin(username="boss"))
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data["code"], "missing_token")

    def test_non_bearer_authorization_rejected(self):
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Basic abc123")
        self.assertEqual(resp.status_code, 401)

    def test_malformed_token_rejected(self):
        # Real verification path (no patch): a non-JWT fails before any network.
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer not-a-real-jwt")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "invalid_token")

    @mock.patch("workforce.scheduler_auth.verify_oidc_token")
    def test_wrong_service_account_rejected(self, mock_verify):
        mock_verify.return_value = valid_claims(email="attacker@evil.example.com")
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer signed-token")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "invalid_token")

    @mock.patch("workforce.scheduler_auth.verify_oidc_token")
    def test_unverified_email_rejected(self, mock_verify):
        mock_verify.return_value = valid_claims(email_verified=False)
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer signed-token")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "invalid_token")

    @mock.patch("workforce.scheduler_auth.verify_oidc_token")
    def test_untrusted_issuer_rejected(self, mock_verify):
        mock_verify.return_value = valid_claims(iss="https://accounts.evil.example")
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer signed-token")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "invalid_token")

    def test_get_method_not_allowed(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


@override_settings(
    WORKFORCE_SCHEDULER_AUDIENCE="",
    WORKFORCE_SCHEDULER_SERVICE_ACCOUNT="",
)
class SchedulerNotConfiguredTests(APITestBase):
    def test_returns_503_when_unconfigured(self):
        url = reverse("workforce_reconcile")
        resp = self.client.post(url, HTTP_AUTHORIZATION="Bearer signed-token")
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.data["code"], "not_configured")


@override_settings(
    WORKFORCE_SCHEDULER_AUDIENCE=AUDIENCE,
    WORKFORCE_SCHEDULER_SERVICE_ACCOUNT=SA_EMAIL,
)
@mock.patch(
    "workforce.scheduler_auth.verify_oidc_token",
    new=lambda token, audience: valid_claims(),
)
class SchedulerExecutionTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("workforce_reconcile")
        self.rep = self.make_sales(username="rep")

    def _post(self):
        return self.client.post(self.url, HTTP_AUTHORIZATION="Bearer scheduler-token")

    def _session(self, employee, last_activity, started=None, window_end=time(21, 0)):
        return WorkSession.objects.create(
            employee=employee,
            policy=None,
            timezone="Asia/Amman",
            daily_target_minutes=180,
            window_start_time=time(9, 0),
            window_end_time=window_end,
            started_at=started or amman(SUNDAY, 9, 0),
            last_activity_at=last_activity,
            work_date=SUNDAY,
        )

    def test_successful_execution_closes_stale_keeps_fresh(self):
        stale = self._session(self.rep, last_activity=amman(SUNDAY, 9, 5))
        fresh_emp = self.make_sales(username="rep2")
        fresh = self._session(fresh_emp, last_activity=amman(SUNDAY, 11, 58))

        with mock.patch("workforce.services.timezone.now", return_value=amman(SUNDAY, 12, 0)):
            resp = self._post()

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")
        self.assertEqual(resp.data["inspected"], 2)
        self.assertEqual(resp.data["closed"], 1)

        stale.refresh_from_db()
        fresh.refresh_from_db()
        self.assertFalse(stale.is_active)
        self.assertEqual(stale.closing_reason, ClosingReason.INACTIVITY)
        self.assertTrue(fresh.is_active)

    def test_idempotent(self):
        session = self._session(self.rep, last_activity=amman(SUNDAY, 9, 5))

        with mock.patch("workforce.services.timezone.now", return_value=amman(SUNDAY, 12, 0)):
            first = self._post()
            self.assertEqual(first.data["closed"], 1)
            session.refresh_from_db()
            ended_at, credited = session.ended_at, session.credited_seconds

            second = self._post()

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["inspected"], 0)
        self.assertEqual(second.data["closed"], 0)
        session.refresh_from_db()
        self.assertEqual(session.ended_at, ended_at)
        self.assertEqual(session.credited_seconds, credited)

    def test_inactivity_closure(self):
        session = self._session(self.rep, last_activity=amman(SUNDAY, 14, 0))

        with mock.patch("workforce.services.timezone.now", return_value=amman(SUNDAY, 15, 0)):
            resp = self._post()

        self.assertEqual(resp.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.closing_reason, ClosingReason.INACTIVITY)
        self.assertTrue(session.auto_closed)
        # Credited up to last_activity + 10 min (14:10), from 09:00 start.
        self.assertEqual(session.ended_at, amman(SUNDAY, 14, 10))
        self.assertEqual(session.credited_seconds, 5 * 3600 + 10 * 60)

    def test_nine_pm_closure(self):
        # Fresh activity at 20:55 (inactivity would not trigger before 21:05),
        # so the hard 9:00 PM window cap is what closes the session.
        session = self._session(self.rep, last_activity=amman(SUNDAY, 20, 55))

        with mock.patch("workforce.services.timezone.now", return_value=amman(SUNDAY, 21, 0)):
            resp = self._post()

        self.assertEqual(resp.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.closing_reason, ClosingReason.WORKING_WINDOW_ENDED)
        self.assertEqual(session.ended_at, amman(SUNDAY, 21, 0))
        self.assertEqual(session.credited_seconds, 12 * 3600)
