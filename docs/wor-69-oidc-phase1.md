# WOR-69 Phase 1 — offline OIDC verification

This PR makes the dormant Roomay authentication boundary reproducibly testable.
It does not register an OIDC client, enable the standalone backend, grant a
Workpeg role, or connect a hosted guest-to-staff request path. WOR-69 remains
open for hosted acceptance.

## Pinned SDK and dependency boundary

`workpeg==0.152.0` supplies `WorkpegAuth.begin()` and `complete()`. Its
`verify_id_token()` imports PyJWT and checks an RS256 signature against a
Workpeg JWKS key, issuer, audience, expiry, and nonce. The SDK wheel does not
declare the optional crypto requirement, so `server-requirements.txt` pins
`PyJWT[crypto]==2.15.1` and `cryptography==50.0.2`. The development requirements
include those server requirements. No OIDC signature check is reimplemented in
Roomay. See the [Workpeg OIDC guide](https://developers.workpeg.com/docs/latest/sign-in-with-workpeg/)
for the provider contract; this repository verifies its installed SDK pin.

## What the offline tests establish

`tests/test_workpeg_oidc.py` generates local RSA keys, signs synthetic ID
tokens, and passes them to the real SDK verifier. Token and JWKS HTTP responses
are mocked, so a valid signature proves local cryptographic verification only.
The tests cover issuer, audience, expiry, nonce, signature, unknown signing
key, state, PKCE verifier forwarding, token endpoint refusal and timeout,
malformed response, callback replay and expiration, business/role rejection,
and local staff-session refusal after a roster binding is revoked. The backend
route tests use only test SQLite and a local request harness.

`tests/test_workpeg_staff_identity.py` verifies the trusted membership port is
queried again on each resolution and a wrong-hotel roster row is refused.
Existing tests cover inactive or missing membership, wrong business, missing
roster match, trusted-port failure, and the rule that a Workpeg admin role does
not grant Roomay administrator privileges. The resolver's membership port is
not connected to a verified production Workpeg membership-refresh API.

## Reproduce

From this worktree with an isolated Python environment, run:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest tests.test_workpeg_oidc tests.test_workpeg_staff_identity tests.test_backend_config -q
python -m unittest tests.test_guest_backend tests.test_function_runtime_readiness -q
python -m compileall -q ui function domain tests backend migrations public_intake
python tools/sync_function_domain.py --check
workpeg ui build ui/
```

The PR's Ubuntu workflow runs `python -m unittest discover -s tests -v` with
temporary PostgreSQL 16 and the remaining Function and UI release checks.
Windows `tests.test_public_intake` has previously hung in the test client;
the supported Linux CI result is the full-suite gate.

## Hosted blockers and next step

The owner and Workpeg must register Roomay's real client and exact HTTPS
callback, confirm client type and subject/business/role semantics, and provide
a supported authoritative membership-refresh and revocation interface. A
signed-in identity does not grant Workpeg Tables access or Roomay privileges.
The standalone backend still refuses startup by default, and no operational
Workpeg writer or Function is activated. After registration, run a separately
approved hosted callback and membership-revocation acceptance test with
fictional development-business identities before wiring WOR-65 delivery.
