# Guest service backend — WOR-15

## Product boundary

The owner has **approved Workpeg Tables as ROOMAY's canonical service-request
and audit store (Option A)**. This branch only introduces a **dormant,
standalone FastAPI/PostgreSQL engineering prototype** of guest requests and
a department inbox. PostgreSQL is the transactional writer *inside isolated
prototype tests only*; it is **not** the hotel's approved operational writer.

The current Workpeg Reception UI instead reads Workpeg request and audit tables.
There is **no automatic copy, write-through, synchronization, or shared staff
inbox** between them. No hotel records can be loaded by this backend until
Workpeg supplies a supported and authorized invocation/read path.
Hotel-dependent routes deliberately respond with sanitized 503 errors. Do not
describe a PostgreSQL request as delivered to staff in Workpeg, enable
guest-facing operations, migrate existing history, or deploy this backend
until Workpeg supports and authorizes the selected **single Workpeg writer**
with verified staff/guest readback. See
[the approved WOR-62 architecture decision](wor-62-pr37-source-of-truth.md).

The existing Workpeg tables and Room 205 records are not changed. The previous
standalone Tables reader and its owner-run verification command have been
removed. Although the general Tables documentation describes developer-token
access for a Peg's own tables, Roomay's owner-recorded Workpeg support reply for
this integration says that `WORKPEG_PK` is not an authorized credential for
this independent backend; the owner reported HTTP 401 on the first read. Until
Workpeg confirms and Roomay approves a supported bridge, the production hotel
snapshot port is unavailable. Hotel-dependent routes return a sanitized 503
and never fall back to synthetic or cached records. Existing table permissions
remain owner-only (`700`).

The canonical room and reservation rows do not currently contain a hotel ID.
The backend therefore enforces one configured hotel binding per Workpeg
business; it cannot safely distinguish multiple hotels inside one business.
Do not onboard a multi-hotel business until the hotel identity mapping is
represented in trusted data and reviewed.
The selected Workpeg business ID is pinned in server configuration and must
match the OIDC callback membership exactly. The application does not accept a
business selector from the browser.

Workpeg OIDC establishes staff identity and selected business membership; it
does not grant standalone Tables access. A Workpeg-submitted Function receives
an invocation-scoped `context["token"]` and `context["business"]`, but no
authenticated external invocation boundary is confirmed. Do not cache or
transport that token into this persistent backend, accept caller-supplied
context, or substitute OIDC tokens for a Tables credential. No Workpeg API is
called by this backend until an approved bridge is implemented.

## Identity and access

### Staff

1. Staff start the official Workpeg OIDC authorization-code flow at
   `/auth/workpeg/start`.
2. Workpeg's SDK `WorkpegAuth.begin()` creates state, PKCE verifier and nonce;
   these are stored server-side and bound to an HttpOnly browser cookie.
3. The callback uses `WorkpegAuth.complete()` to validate state and the OIDC
   response. The selected Workpeg membership supplies an opaque subject,
   business UUID and Workpeg membership role.
4. Roomay accepts only owner/admin/member memberships that match an active
   server-controlled hotel binding and an active `staff_bindings` row keyed by
   the configured business plus Workpeg subject. Department and Roomay privileges come only
   from that local mapping; browser claims are never accepted.
5. Staff sessions are random, HttpOnly, `SameSite=Strict`, server-side hashed,
   and expire after 15 minutes. Disabling the local mapping revokes access on
   the next request. Workpeg membership removal is not rechecked on every API
   request; its maximum residual access window is the 15-minute session TTL.

The owner-run `python -m backend.bootstrap_staff` command requires an already
verified OIDC subject and an explicit business, hotel, department and allowed
Roomay privilege set. It writes only the Roomay PostgreSQL authorization
mapping. Do not put email addresses or roles supplied by a browser into that
command. A two-person review or equivalent owner approval is recommended for
production mapping changes.

For first setup only, an owner may set
`ROOMAY_BOOTSTRAP_OWNER_ENABLED=true`. If no Roomay staff mappings exist, the
first authenticated Workpeg **business owner** for the pinned business receives
the initial Reception manager/request-admin mapping using the configured
hotel UUID. The switch does nothing once any mapping exists and is disabled by
default; turn it off after the first successful owner login. Ordinary Workpeg
members never bootstrap themselves and need an owner-provisioned department
mapping.

### Guests

1. A locally authorized receptionist issues an invitation only after checking
   the registered occupant against the guest's on-file contact or in-person
   hotel procedure. The backend reads the current Workpeg snapshot and checks
   the exact active stay, room and registered occupant.
2. The invitation is a random, one-time secret. Only its hash is stored; the
   plaintext is returned once with `Cache-Control: no-store`, and the backend
   explicitly says delivery was not sent. Staff must deliver it only through
   the hotel's independently verified contact channel. No SMS/email provider
   is configured here.
3. Redeeming it consumes it once and creates a stay-scoped, hashed, HttpOnly
   guest session with a 30-minute TTL. Guest actions re-read Workpeg and check
   that the same guest remains a registered occupant of the same checked-in
   stay and room. Guest sessions can be explicitly revoked or expire.

Room numbers, URLs, caller IDs, AI outputs and client-supplied guest/stay IDs
never authenticate a guest. This first slice does not automate contact
verification or message delivery; the human receptionist verification step
is a deployment prerequisite and operational risk.

## Persistence and audit

- Guest request content is validated by the existing `domain.service_requests`
  contract and routed by `route_category`.
- Preparation writes a short-lived proposal only; the request is not created
  until the guest explicitly confirms that exact proposal.
- A session-scoped idempotency key returns the same proposal for an exact
  retry and rejects changed content. Confirmation locks the proposal row.
- PostgreSQL stores the request plus its initial committed audit event inside
  one transaction. Unique constraints protect request idempotency, audit
  sequence, event identity and operation identity. Subsequent staff
  transitions lock the request and audit rows, validate the complete committed
  history with the existing domain rule, and append the next event in the same
  transaction.
- Read-back validation verifies the request/audit chain before returning a
  request reference or success state. A failed/uncertain write returns a
  sanitized unavailable result and is never automatically retried. Retrying
  the same confirmation handle reconciles through the unique identity and
  committed audit chain.
- A relational transaction is the serialization boundary. The SQLite tests
  are isolated test storage only; they do not prove PostgreSQL row-lock
  behavior. PostgreSQL integration/concurrency verification remains required.

Guest response projections omit guest, stay and room entity IDs. Staff
projections include the human room number and request details needed for the
routed department but exclude guest identity, stay identity and audit payload.
Free-text descriptions can still contain personal information; production
retention, access monitoring and departmental staff training remain required.

## Local development

Requirements: Docker Desktop running, Python 3.10+, an owner-configured
Workpeg OIDC client, exact development business and hotel UUIDs, and a local
HTTPS origin. `WORKPEG_PK` and a Peg UUID are not backend runtime settings.
No standalone hotel-data bridge is currently configured, so hotel-dependent
routes stay unavailable. Keep any confidential-client secret outside Git,
browser code, shell history, test fixtures and logs.

1. Copy `.env.example` to ignored `.env`, set a strong random local database
   password, and set `ROOMAY_DATABASE_URL` to the same password. URL-encode
   password characters such as `@`, `:` or `/` inside the DSN.
2. Start only the loopback-bound local database: `docker compose up -d roomay-db`.
3. Install dependencies with `python -m pip install -r server-requirements.txt`.
4. Have the owner choose the actual local HTTPS host and port and provide the
   OIDC client registration outcome. Set `ROOMAY_PUBLIC_BASE_URL` to that
   browser-visible origin and set `ROOMAY_OIDC_REDIRECT_URI` to the exact
   registered URI `<ROOMAY_PUBLIC_BASE_URL>/auth/workpeg/callback`. Keep
   `ROOMAY_COOKIE_SECURE=true`. The public Workpeg docs describe OIDC and SDK
   flow, not the owner-specific registration procedure. Do not submit example
   or placeholder callback URLs. See [WOR-61 local authentication](wor-61-local-auth.md).
5. Apply the explicit schema migration with `alembic upgrade head`.
6. Run behind a trusted HTTPS reverse proxy using
   `uvicorn backend.main:app --host 127.0.0.1 --port 8080 --no-access-log`.
   The OIDC callback contains a short-lived authorization code in its URL;
   keep query strings redacted from reverse-proxy and platform access logs.
7. Open `/staff`, sign in with Workpeg, and verify the authorized department
   inbox. For guest access, a mapped receptionist issues and securely delivers
   a one-time invitation to a guest whose active stay they have verified.

### Request limits and reverse-proxy boundary

The backend enforces rolling one-hour quotas in PostgreSQL: 20 guest request
preparations per guest session, 20 invitations issued per mapped staff actor,
and 120 new staff lifecycle transitions per mapped staff actor. Existing
idempotent retries remain reconcilable. The quota checks lock the corresponding
guest-session or staff-binding row inside the same transaction, so concurrent
workers cannot all pass the same count. A rejected transition rolls back its
request and audit changes. These limits are application controls, not a
substitute for edge abuse protection.

Unauthenticated OIDC start/callback and invitation-redemption traffic still
requires IP-based throttling and request-body size limits at a trusted HTTPS
reverse proxy or ingress. Roomay does not trust `X-Forwarded-For` or similar
client headers as identity, and it does not yet implement its own trusted-proxy
IP parser or distributed pre-authentication limiter. Do not expose Uvicorn
directly to the internet. Configure the proxy to overwrite forwarded headers,
rate-limit these routes, cap request bodies and header sizes, enforce TLS, and
redact callback query strings from logs. Keep the Uvicorn listener on loopback
or a private network reachable only from that proxy. Verify proxy trust and
limits in the selected deployment before production.

Staff sessions are rechecked against local authorization mappings on each
request; mapping revocation takes effect on the next call. Workpeg membership
revocation is not live-polled and can remain effective until the 15-minute
staff-session expiry. Guest sessions expire after 30 minutes, are revocable,
and active stay/occupant scope is re-read from Workpeg for each protected
guest action.

The Postgres 16 acceptance suite (`python -m unittest
tests.test_backend_postgres -v`) runs only when `ROOMAY_TEST_DATABASE_URL` is
set to the loopback Compose database at `127.0.0.1:55432/roomay`. It applies
the current Alembic migration in a randomly named, per-test schema, runs the
real route handlers, and drops only that exact temporary schema afterward.
It refuses other hosts, ports, database names, or PostgreSQL major versions.
On Windows, load the DSN from the ignored `.env` into
`$env:ROOMAY_TEST_DATABASE_URL` for the command and remove it from the
environment afterward; do not print the DSN or pass it as a literal command
argument.

Never expose the backend directly to the public internet without TLS,
rate-limiting, request-size limits, secure secret management, monitoring,
backup/restore, retention controls and an incident-response plan. The app
checks same-origin on state-changing routes but deployment still needs proxy
and host configuration review.

## Verification status and go-live gates

Offline tests use synthetic hotel data through a test-only reader, a mock OIDC
identity result and isolated SQLite/PostgreSQL schemas. They verify route
policy, guest-session scope, idempotency, persistence across DB sessions,
committed audit history, department routing, privacy projection and
failed-write rollback. They also verify that the production default hotel-data
port returns unavailable without creating guest requests. Tests do not verify
Workpeg, an actual OIDC client registration, an authorized hotel-data bridge,
production deployment or message delivery.

Before an owner-authorized real development test:

1. Obtain Workpeg's supported, authenticated external invocation mechanism,
   including caller identity/business authorization, replay and expiry rules.
   Do not use `WORKPEG_PK` or export an invocation-scoped Function token.
2. Register the exact owner-selected OIDC callback and confirm staff
   membership claims in the provider's test account. OIDC does not authorize
   hotel-table reads.
3. Run PostgreSQL migrations and concurrency/rollback integration tests on
   the same Postgres major version selected for deployment.
4. Map one staff subject to Reception and one to Housekeeping; test cross-
   department denial and immediate local mapping revocation.
5. Use a separately verified fictional guest contact and a currently active
   fictional stay. Create one explicitly approved guest request, reload in a
   separate session, verify the department inbox and committed audit, and
   test duplicate confirmation/recovery after a simulated lost response.
6. Confirm an unauthorized staff account is denied and that neither guest nor
   staff projections expose protected identity or audit fields.

Existing owner-only Workpeg request/audit tables remain untouched.
The owner **selected Workpeg Tables as the canonical operational source of
truth** in [WOR-62](wor-62-pr37-source-of-truth.md), but the vendor-backed
external guest ingestion path is still **unverified**. Do not deprecate or
bypass Workpeg tables, create competing writers, or broaden permissions
(`700`) to make the prototype operate.

### Current GitHub verification (12 November 2026)

PR #37 has been reconciled with protected `main`, preserving all existing
hotel safety rules, main-only workflow triggers, compiled UI/release gate,
and voice smoke checks. GitHub Actions now starts a temporary **PostgreSQL 16**
service on its isolated runner at `127.0.0.1:55432` and runs migrations,
transactions, concurrency and restart-style DB readback integration via
`tests/test_backend_postgres.py` within `python -m unittest discover -s tests -v`.
A hardcoded ephemeral test-only database password is **not** a hosted secret.
For a local replica, use the documented Compose database and set
`ROOMAY_TEST_DATABASE_URL` to its **loopback** connection; tests refuse a
nonlocal host, wrong port, database name, and non-16 server.

**Passing CI proves PostgreSQL behavior in an isolated test service, not a
registered Workpeg OIDC client, real staff role authorizations, a hotel-data
bridge, Workpeg writes, guest-to-staff delivery, or public release readiness.**
The PR remains draft until these integration contracts are approved and
hosted acceptance is obtained.

### Standalone backend startup is explicitly disabled

The merged source code is **infrastructure only**. Importing `backend.main`
or running `uvicorn backend.main:app` fails with
`standalone_guest_backend_disabled_pending_workpeg_integration` unless a
developer explicitly sets `ROOMAY_ENABLE_STANDALONE_PROTOTYPE=local-only`.
That value is meant solely for an isolated development experiment; it is
**not** a Workpeg credential, a deploy flag, production authorization, or
proof that guests reach staff. Even with that flag, the default Workpeg
hotel-data adapter is unavailable and guest/staff hotel routes return 503.
No public ingress, Workpeg rights or deployment is approved by merging PR #37.
