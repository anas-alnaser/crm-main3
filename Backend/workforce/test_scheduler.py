"""Tests for the internal scheduler reconciliation endpoint and its OIDC auth.

Google's token verification (``verify_oidc_token``) is always mocked — the suite
never contacts Google or Cloud Scheduler. Coverage:

  * missing bearer token -> 401
  * malformed token -> 403
  * valid Google-token verification -> 200
  * wrong audience / wrong issuer / wrong service account / unverified email /
    expired token / bad signature -> 403 (generic response)
  * certificate/network verification failure -> safe rejection (503, never 200)
  * endpoint ignores body/query user ids and timestamps
  * reconciliation is idempotent; inactivity and 9 PM closure work end-to-end
  * no token or Authorization value is ever written to the logs
  * unit coverage for the error categoriser and the cert-caching transport
"""
from datetime import date, time
from unittest import mock

from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from crm.apitestbase import APITestBase
from workforce import scheduler_auth
from workforce.models import ClosingReason, WorkSession
from workforce.timezones import combine_local

SUNDAY = date(2026, 8, 2)  # a working day in Asia/Amman
SA_EMAIL = "crm-scheduler@crm-morph-fuel.iam.gserviceaccount.com"
AUDIENCE = "https://crm-morph-fuel-api.example.run.app/internal/workforce/reconcile/"


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

    # --- unauthenticated ---------------------------------------------------
    def test_missing_token_rejected(self):
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data["code"], "missing_token")

    def test_authenticated_browser_user_cannot_invoke(self):
        # An admin logged into the SPA/admin carries no scheduler OIDC token.
        self.auth(self.make_admin(username="boss"))
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data["code"], "missing_token")

    def test_non_bearer_authorization_rejected(self):
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Basic abc123")
        self.assertEqual(resp.status_code, 401)

    # --- invalid tokens (verifier failures) --------------------------------
    @mock.patch("workforce.scheduler_auth.verify_oidc_token")
    def test_malformed_token_rejected(self, mock_verify):
        mock_verify.side_effect = ValueError("Wrong number of segments in token: b'x'")
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer not-a-jwt")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "invalid_token")

    @mock.patch("workforce.scheduler_auth.verify_oidc_token")
    def test_wrong_audience_rejected(self, mock_verify):
        mock_verify.side_effect = ValueError("Token has wrong audience x, expected y")
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer signed")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "invalid_token")

    @mock.patch("workforce.scheduler_auth.verify_oidc_token")
    def test_expired_token_rejected(self, mock_verify):
        mock_verify.side_effect = ValueError("Token expired, 100 < 200")
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer signed")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "invalid_token")

    @mock.patch("workforce.scheduler_auth.verify_oidc_token")
    def test_bad_signature_rejected(self, mock_verify):
        mock_verify.side_effect = ValueError("Could not verify token signature.")
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer signed")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "invalid_token")

    @mock.patch("workforce.scheduler_auth.verify_oidc_token")
    def test_verifier_wrong_issuer_rejected(self, mock_verify):
        mock_verify.side_effect = ValueError("Wrong issuer.")
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer signed")
        self.assertEqual(resp.status_code, 403)

    # --- invalid identity (verifier succeeds, identity fails) --------------
    @mock.patch("workforce.scheduler_auth.verify_oidc_token")
    def test_untrusted_issuer_claim_rejected(self, mock_verify):
        mock_verify.return_value = valid_claims(iss="https://accounts.evil.example")
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer signed")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "invalid_token")

    @mock.patch("workforce.scheduler_auth.verify_oidc_token")
    def test_wrong_service_account_rejected(self, mock_verify):
        mock_verify.return_value = valid_claims(email="attacker@evil.example.com")
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer signed")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "invalid_token")

    @mock.patch("workforce.scheduler_auth.verify_oidc_token")
    def test_unverified_email_rejected(self, mock_verify):
        mock_verify.return_value = valid_claims(email_verified=False)
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer signed")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data["code"], "invalid_token")

    # --- verification unavailable (never fail open) ------------------------
    @mock.patch("workforce.scheduler_auth.verify_oidc_token")
    def test_cert_fetch_failure_is_safe_rejection(self, mock_verify):
        mock_verify.side_effect = RuntimeError("cert endpoint unreachable")
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer signed")
        self.assertNotEqual(resp.status_code, 200)  # must never fail open
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.data["code"], "unavailable")

    # --- valid --------------------------------------------------------------
    @mock.patch("workforce.scheduler_auth.verify_oidc_token")
    def test_valid_token_executes_and_uses_configured_audience(self, mock_verify):
        mock_verify.return_value = valid_claims()
        resp = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer good-token")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")
        # The token from the header is verified against the configured audience.
        args, _ = mock_verify.call_args
        self.assertEqual(args[0], "good-token")
        self.assertEqual(args[1], AUDIENCE)

    def test_get_method_not_allowed(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)

    # --- no secret leakage in logs -----------------------------------------
    @mock.patch("workforce.scheduler_auth.verify_oidc_token")
    def test_token_never_appears_in_logs(self, mock_verify):
        secret = "SUPERSECRETTOKENVALUE.aaa.bbb"
        mock_verify.return_value = valid_claims(email="attacker@evil.example.com")
        with self.assertLogs("workforce", level="WARNING") as cm:
            self.client.post(self.url, HTTP_AUTHORIZATION=f"Bearer {secret}")
        joined = "\n".join(cm.output)
        self.assertNotIn(secret, joined)               # token absent
        self.assertNotIn("Bearer", joined)             # header absent
        self.assertIn("wrong_service_account", joined)  # only the category logged


@override_settings(
    WORKFORCE_SCHEDULER_AUDIENCE="",
    WORKFORCE_SCHEDULER_SERVICE_ACCOUNT="",
)
class SchedulerNotConfiguredTests(APITestBase):
    def test_returns_503_when_unconfigured(self):
        url = reverse("workforce_reconcile")
        resp = self.client.post(url, HTTP_AUTHORIZATION="Bearer signed")
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

    def _post(self, body=None):
        if body is None:
            return self.client.post(self.url, HTTP_AUTHORIZATION="Bearer scheduler-token")
        return self.client.post(
            self.url, body, format="json", HTTP_AUTHORIZATION="Bearer scheduler-token"
        )

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
        self.assertEqual(resp.data["inspected"], 2)
        self.assertEqual(resp.data["closed"], 1)
        stale.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(stale.closing_reason, ClosingReason.INACTIVITY)
        self.assertTrue(fresh.is_active)

    def test_body_user_id_and_timestamp_are_ignored(self):
        stale = self._session(self.rep, last_activity=amman(SUNDAY, 9, 5))
        other = self.make_sales(username="rep2")
        fresh = self._session(other, last_activity=amman(SUNDAY, 11, 58))

        # A crafted body tries to smuggle a target user and a fake "now" far in
        # the past (which, if honored, would credit nothing / close nothing).
        malicious_body = {
            "employee": other.id,
            "user_id": 999,
            "now": "2000-01-01T00:00:00Z",
            "work_date": "2000-01-01",
            "closed": 999,
        }
        with mock.patch("workforce.services.timezone.now", return_value=amman(SUNDAY, 12, 0)):
            resp = self._post(malicious_body)

        self.assertEqual(resp.status_code, 200)
        # Server clock (12:00), not the body's 2000 timestamp, governs closure.
        self.assertEqual(resp.data["closed"], 1)
        stale.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(stale.closing_reason, ClosingReason.INACTIVITY)
        self.assertTrue(fresh.is_active)  # the body's target user was not touched

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
        self.assertEqual(session.ended_at, amman(SUNDAY, 14, 10))
        self.assertEqual(session.credited_seconds, 5 * 3600 + 10 * 60)

    def test_nine_pm_closure(self):
        session = self._session(self.rep, last_activity=amman(SUNDAY, 20, 55))
        with mock.patch("workforce.services.timezone.now", return_value=amman(SUNDAY, 21, 0)):
            resp = self._post()
        self.assertEqual(resp.status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.closing_reason, ClosingReason.WORKING_WINDOW_ENDED)
        self.assertEqual(session.ended_at, amman(SUNDAY, 21, 0))
        self.assertEqual(session.credited_seconds, 12 * 3600)


class ErrorCategoriserTests(SimpleTestCase):
    def test_categories(self):
        cat = scheduler_auth._categorize_value_error
        self.assertEqual(cat(ValueError("Token expired, 1<2")), "expired_token")
        self.assertEqual(cat(ValueError("Token has wrong audience a, expected b")), "wrong_audience")
        self.assertEqual(cat(ValueError("Wrong issuer.")), "wrong_issuer")
        self.assertEqual(cat(ValueError("Could not verify token signature.")), "invalid_signature")
        self.assertEqual(cat(ValueError("Wrong number of segments in token")), "malformed_token")
        self.assertEqual(cat(ValueError("something else entirely")), "invalid_token")


class _FakeResp:
    def __init__(self, status=200, headers=None):
        self.status = status
        self.headers = headers or {}


class MaxAgeParsingTests(SimpleTestCase):
    def test_parses_max_age(self):
        self.assertEqual(scheduler_auth._max_age_seconds({"Cache-Control": "public, max-age=3600"}), 3600)

    def test_subtracts_age(self):
        self.assertEqual(
            scheduler_auth._max_age_seconds({"Cache-Control": "max-age=3600", "Age": "100"}), 3500
        )

    def test_missing_or_zero(self):
        self.assertEqual(scheduler_auth._max_age_seconds({}), 0)
        self.assertEqual(scheduler_auth._max_age_seconds(None), 0)
        self.assertEqual(scheduler_auth._max_age_seconds({"Cache-Control": "max-age=0"}), 0)
        self.assertEqual(scheduler_auth._max_age_seconds({"Cache-Control": "no-store"}), 0)


class RealVerifierIntegrationTests(SimpleTestCase):
    """Exercise the real google-auth verifier offline (only the certificate
    transport is stubbed). Guards the regression where RS256 verification had no
    crypto backend and rejected every genuine token."""

    def _mint(self, audience, kid="kid-1", **claim_overrides):
        import datetime as dt
        import json
        import time as _time

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        from google.auth import crypt, jwt as gjwt

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
        now = dt.datetime.now(dt.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=1))
            .sign(key, hashes.SHA256())
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()

        signer = crypt.RSASigner.from_string(priv_pem, kid)
        epoch = int(_time.time())
        payload = {
            "iss": "https://accounts.google.com",
            "aud": audience,
            "email": SA_EMAIL,
            "email_verified": True,
            "sub": "1",
            "iat": epoch,
            "exp": epoch + 3600,
        }
        payload.update(claim_overrides)
        token = gjwt.encode(signer, payload).decode()

        class _Resp:
            status = 200
            data = json.dumps({kid: cert_pem}).encode()
            headers = {"Cache-Control": "public, max-age=3600"}

        def fake_request(url, method="GET", body=None, headers=None, **kw):
            return _Resp()

        return token, fake_request

    def test_valid_token_verifies(self):
        token, fake_request = self._mint(AUDIENCE)
        with mock.patch.object(scheduler_auth, "_get_verifier_request", return_value=fake_request):
            claims = scheduler_auth.verify_oidc_token(token, AUDIENCE)
        self.assertEqual(claims["email"], SA_EMAIL)
        self.assertEqual(claims["aud"], AUDIENCE)

    def test_wrong_audience_token_rejected_by_real_verifier(self):
        token, fake_request = self._mint("https://someone-else/aud/")
        with mock.patch.object(scheduler_auth, "_get_verifier_request", return_value=fake_request):
            with self.assertRaises(ValueError):
                scheduler_auth.verify_oidc_token(token, AUDIENCE)


class CachingRequestTests(SimpleTestCase):
    def test_caches_get_within_max_age(self):
        calls = []

        def inner(url, method="GET", body=None, headers=None, **kw):
            calls.append(url)
            return _FakeResp(200, {"Cache-Control": "public, max-age=3600"})

        req = scheduler_auth._CachingRequest(inner)
        first = req("https://certs")
        second = req("https://certs")
        self.assertIs(first, second)
        self.assertEqual(len(calls), 1)  # served from cache the second time

    def test_refetches_after_expiry(self):
        calls = []

        def inner(url, method="GET", body=None, headers=None, **kw):
            calls.append(url)
            return _FakeResp(200, {"Cache-Control": "max-age=100"})

        req = scheduler_auth._CachingRequest(inner)
        with mock.patch.object(scheduler_auth.time, "monotonic", return_value=1000.0):
            req("u")
        with mock.patch.object(scheduler_auth.time, "monotonic", return_value=1050.0):
            req("u")  # within ttl -> cached
        with mock.patch.object(scheduler_auth.time, "monotonic", return_value=1200.0):
            req("u")  # ttl elapsed -> refetch
        self.assertEqual(len(calls), 2)

    def test_does_not_cache_non_200_or_uncacheable(self):
        calls = []

        def inner(url, method="GET", body=None, headers=None, **kw):
            calls.append((url, method))
            return _FakeResp(500, {"Cache-Control": "max-age=3600"})

        req = scheduler_auth._CachingRequest(inner)
        req("https://certs")
        req("https://certs")
        self.assertEqual(len(calls), 2)  # 500 responses are never cached
