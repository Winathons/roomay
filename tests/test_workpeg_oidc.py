"""Offline OIDC verification using WorkpegAuth and synthetic RSA identities.

JWT signatures below are real RS256 signatures from locally generated keys.
Only the Workpeg token and JWKS HTTP endpoints are mocked; no live provider is
contacted. SQLite and the app's route harness are test-only fixtures.
"""
from datetime import datetime, timedelta, timezone
import base64
import hashlib
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
import requests
from workpeg.auth import WorkpegAuth, WorkpegAuthError

from backend.app import _digest
from backend.models import OIDCState, StaffBinding
from tests import test_guest_backend as guest_backend_tests

LocalClient = guest_backend_tests.LocalClient
AT = guest_backend_tests.AT


ISSUER = "https://identity.workpeg.test"
CLIENT_ID = "roomay-test-client"


def signing_material(kid="local-key"):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    public_jwk.update(kid=kid, use="sig", alg="RS256")
    return private, {"keys": [public_jwk]}


class OIDCAppFixture(TestCase):
    """Use the existing isolated SQLite fixture without inheriting its tests."""
    def _configure_fixture(self, *args, **kwargs):
        return guest_backend_tests.GuestBackendTests._configure_fixture(
            self, *args, **kwargs)

    def setUp(self):
        guest_backend_tests.GuestBackendTests.setUp(self)
        self.private, self.jwks = signing_material()
        self.auth = WorkpegAuth(client_id=CLIENT_ID, client_secret="offline-secret",
                                redirect_uri=self.origin + "/auth/workpeg/callback",
                                issuer=ISSUER)
        self.settings.oidc_client_id = CLIENT_ID
        self.settings.oidc_client_secret = "offline-secret"
        self.app = __import__("backend.app", fromlist=["create_app"]).create_app(
            session_factory=self.sessions, hotel_reader=self.reader,
            settings=self.settings, clock=lambda: AT, workpeg_auth=self.auth)
        self.client = LocalClient(self.app, base_url=self.origin)

    def tearDown(self):
        guest_backend_tests.GuestBackendTests.tearDown(self)

    def claims(self, **changes):
        now = datetime.now(timezone.utc)
        claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": "wp-subject-reception",
                  "workpeg_business_id": guest_backend_tests.BUSINESS_ID,
                  "workpeg_business_name": "Test business", "workpeg_role": "member",
                  "nonce": "", "iat": int(now.timestamp()),
                  "exp": int((now + timedelta(minutes=5)).timestamp())}
        claims.update(changes)
        return claims

    def signed(self, claims=None, key=None, kid="local-key"):
        return jwt.encode(claims or self.claims(), key or self.private,
                          algorithm="RS256", headers={"kid": kid})

    def provider(self, token, *, jwks=None, status=200, body=None):
        token_response = Mock(status_code=status)
        token_response.json.return_value = body if body is not None else {"id_token": token}
        keys_response = Mock(status_code=200)
        keys_response.json.return_value = jwks or self.jwks
        return patch("workpeg.auth.requests.post", return_value=token_response), \
            patch("workpeg.auth.requests.get", return_value=keys_response)

    def test_real_signature_claim_verification_and_provider_is_mocked(self):
        start = self.auth.begin()
        token = self.signed(self.claims(nonce=start.nonce))
        post, get = self.provider(token)
        with post as mocked_post, get as mocked_get:
            identity = self.auth.complete(code="offline-code", state=start.state, start=start)
        self.assertEqual(identity.subject, "wp-subject-reception")
        self.assertEqual(identity.business_id, guest_backend_tests.BUSINESS_ID)
        self.assertEqual(identity.role, "member")
        self.assertEqual(mocked_post.call_args.kwargs["json"]["code_verifier"], start.code_verifier)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(
            start.code_verifier.encode()).digest()).rstrip(b"=").decode()
        authorize = parse_qs(urlparse(start.url).query)
        self.assertEqual(authorize["code_challenge"], [challenge])
        self.assertEqual(authorize["code_challenge_method"], ["S256"])
        self.assertEqual(mocked_get.call_count, 1)

    def test_invalid_signature_unknown_kid_and_claim_failures(self):
        other, _ = signing_material("other-key")
        cases = [
            ("bad_signature", self.signed(self.claims(nonce="n"), key=other)),
            ("unknown_kid", self.signed(self.claims(nonce="n"), kid="unknown")),
            ("expired", self.signed(self.claims(
                nonce="n", exp=int((datetime.now(timezone.utc)-timedelta(seconds=1)).timestamp())))),
            ("wrong_issuer", self.signed(self.claims(iss="https://wrong.test", nonce="n"))),
            ("wrong_audience", self.signed(self.claims(aud="wrong-client", nonce="n"))),
            ("wrong_nonce", self.signed(self.claims(nonce="different"))),
        ]
        for label, token in cases:
            with self.subTest(failure=label):
                with patch("workpeg.auth.requests.get", return_value=Mock(status_code=200, json=lambda: self.jwks)):
                    with self.assertRaises(WorkpegAuthError):
                        self.auth.verify_id_token(token, nonce="n")

    def test_state_pkce_replay_and_expired_authorization_state(self):
        start = self.auth.begin()
        with patch("workpeg.auth.requests.post", side_effect=AssertionError("provider must not be contacted")):
            with self.assertRaises(WorkpegAuthError):
                self.auth.complete(code="offline-code", state="wrong", start=start)
        altered = type(start)(url=start.url, state=start.state,
                              code_verifier="wrong-verifier", nonce=start.nonce)
        with patch("workpeg.auth.requests.post") as post:
            post.return_value = Mock(status_code=400, json=lambda: {"error": "invalid_grant"})
            with self.assertRaises(WorkpegAuthError):
                self.auth.complete(code="offline-code", state=start.state, start=altered)
            self.assertEqual(post.call_args.kwargs["json"]["code_verifier"], "wrong-verifier")
        # The real callback consumes state once and rejects replay/expiry.
        with self.sessions.begin() as db:
            row = OIDCState(state_hash=_digest("expired-state"), nonce="n", verifier="v",
                            browser_hash=_digest("expired-browser"), created_at=AT-timedelta(minutes=11))
            db.add(row)
        self.client.cookies["roomay_oidc"] = "expired-browser"
        with patch("workpeg.auth.requests.post", side_effect=AssertionError("provider must not be contacted")):
            expired = self.client.get("/auth/workpeg/callback", params={"code": "c", "state": "expired-state"})
        self.assertEqual(expired.status_code, 400)

    def test_business_and_role_are_rejected_after_valid_oidc(self):
        for claims in (self.claims(nonce="", workpeg_business_id=str(uuid4())),
                       self.claims(nonce="", workpeg_role="guest")):
            with self.subTest(claims=claims):
                # callback nonce is supplied only after begin, so install a token response dynamically
                begun = self.client.get("/auth/workpeg/start")
                state = parse_qs(urlparse(begun.headers["location"]).query)["state"][0]
                with self.sessions() as db:
                    saved = db.query(OIDCState).filter_by(state_hash=_digest(state)).one()
                    claims["nonce"] = saved.nonce
                token = self.signed(claims)
                post, get = self.provider(token)
                with post, get:
                    response = self.client.get("/auth/workpeg/callback", params={"code": "c", "state": state})
                self.assertEqual(response.status_code, 403)

    def test_token_endpoint_timeout_rejection_and_malformed_response(self):
        start = self.auth.begin()
        with patch("workpeg.auth.requests.post", side_effect=requests.Timeout("synthetic timeout")):
            with self.assertRaises(requests.Timeout):
                self.auth.complete(code="c", state=start.state, start=start)
        for response in (Mock(status_code=401, json=lambda: {"error": "invalid_client"}),
                         Mock(status_code=200, json=lambda: {"unexpected": True}),
                         Mock(status_code=200, json=Mock(side_effect=ValueError("not json")))):
            with patch("workpeg.auth.requests.post", return_value=response):
                with self.assertRaises(WorkpegAuthError):
                    self.auth.complete(code="c", state=start.state, start=start)

    def test_callback_provider_failures_are_sanitized_and_never_issue_session(self):
        scenarios = (
            ("timeout", requests.Timeout("synthetic timeout"), 503),
            ("rejection", Mock(status_code=401, json=lambda: {"error": "invalid_client"}), 401),
            ("malformed", Mock(status_code=200, json=lambda: {"unexpected": True}), 401),
        )
        for label, provider_result, expected_status in scenarios:
            with self.subTest(failure=label):
                started = self.client.get("/auth/workpeg/start")
                state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
                with patch("workpeg.auth.requests.post", side_effect=provider_result
                           if isinstance(provider_result, Exception) else None,
                           return_value=None if isinstance(provider_result, Exception) else provider_result):
                    response = self.client.get("/auth/workpeg/callback",
                                               params={"code": "offline", "state": state})
                self.assertEqual(response.status_code, expected_status)
                self.assertNotIn("roomay_staff", self.client.cookies)

    def test_session_refused_after_staff_binding_revoked(self):
        started = self.client.get("/auth/workpeg/start")
        state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
        with self.sessions() as db:
            saved = db.query(OIDCState).filter_by(state_hash=_digest(state)).one()
            nonce = saved.nonce
            verifier = saved.verifier
        token = self.signed(self.claims(nonce=nonce))
        post, get = self.provider(token)
        with post as mocked_post, get:
            response = self.client.get("/auth/workpeg/callback",
                                       params={"code": "good-code", "state": state})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(mocked_post.call_args.kwargs["json"]["code_verifier"], verifier)
        self.assertIn("roomay_staff", self.client.cookies)
        replay = self.client.get("/auth/workpeg/callback",
                                 params={"code": "good-code", "state": state})
        self.assertEqual(replay.status_code, 400)
        self.assertIn("roomay_staff", self.client.cookies)
        with self.sessions.begin() as db:
            binding = db.query(StaffBinding).filter_by(workpeg_subject="wp-subject-reception").one()
            binding.active = False
        denied = self.client.get("/staff/requests")
        self.assertEqual(denied.status_code, 403)
