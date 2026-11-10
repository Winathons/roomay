# Guest service backend — WOR-15

## Product boundary

This branch introduces a real HTTPS application backend for guest service
requests and the department inbox. **PostgreSQL is the single source of truth
for requests and their audit history created through this backend.** Workpeg is
read-only for hotel rooms, guests, reservations, stays and registered
occupants. There is no automatic copy, write-through, or dual-writer to the
existing Workpeg request tables. Historical Workpeg request rows therefore do
not appear in this new inbox. An owner-reviewed migration is required before
any existing Workpeg request history is moved or treated as authoritative.

The existing Workpeg tables and Room 205 records are not changed. `WORKPEG_PK`
is used only by the server-side snapshot reader. The reader requires all seven
hotel tables to be readable, exact-contract compatible, permission `700`, and
owned by the configured Roomay Peg ID. Any mismatch, inaccessible table,
malformed page, or invalid snapshot fails closed. It does not fall back to
fixtures.

The canonical room and reservation rows do not currently contain a hotel ID.
The backend therefore enforces one configured hotel binding per Workpeg
business; it cannot safely distinguish multiple hotels inside one business.
Do not onboard a multi-hotel business until the hotel identity mapping is
represented in trusted data and reviewed.
The selected Workpeg business ID is pinned in server configuration and must
match the OIDC callback membership exactly. The application does not accept a
business selector from the browser.

Workpeg documentation permits `WORKPEG_PK` backend access only for Peg-owned
tables in businesses where the Peg is installed. The nine tables' actual `peg`
metadata and installed-business reachability have not been inspected by this
code change, and no Workpeg API was called. As a result, the Workpeg read path
must still be verified by the owner in the development business before a real
guest session can work.

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

Requirements: Docker Desktop running, Python 3.10+, and an owner-configured
Workpeg OIDC client plus a server-only `WORKPEG_PK` for the approved Roomay
Peg, exact development business UUID and canonical Peg UUID from Workpeg table
metadata. The UUID is normalized to lowercase before comparison. Do not place secrets in browser code, Git, shell history, test fixtures or
logs. The Workpeg key must come from an approved secret manager and must never
be generated or pasted into a tracked `.env` file.

1. Copy `.env.example` to ignored `.env`, set a strong random local database
   password, and set `ROOMAY_DATABASE_URL` to the same password. URL-encode
   password characters such as `@`, `:` or `/` inside the DSN.
2. Start only the loopback-bound local database: `docker compose up -d roomay-db`.
3. Install dependencies with `python -m pip install -r server-requirements.txt`.
4. Load backend environment variables from a local secret manager; configure
   OIDC callback and public base URLs to use HTTPS. `ROOMAY_COOKIE_SECURE=true`
   is required outside isolated tests. Before OIDC setup, the server-side hotel read path can be checked without
   starting the application or opening a session. Inject `WORKPEG_PK`,
   `ROOMAY_WORKPEG_PEG_ID`, and `ROOMAY_WORKPEG_BUSINESS_ID` from the approved
   secret/configuration source, then run
   `python -m backend.verify_workpeg_readonly`. This makes only Workpeg GET
   requests, validates all seven canonical hotel table schemas, Peg ownership,
   permission `700`, pagination and snapshot relationships, and prints only
   sanitized pass/fail, aliases and row counts. It never prints row contents,
   IDs or credentials. A successful read proves this Peg can access those
   tables in that business; separately confirm the installation in the
   Workpeg business dashboard. Missing configuration fails before any request.
   If it fails, rerun with `--diagnostic` to opt in to the failing stage,
   canonical alias, HTTP status or safe status category, and stable allowlisted
   error code. Normal mode keeps its generic failure response; diagnostics do
   not include response bodies or arbitrary exception details.
5. Apply the explicit schema migration with `alembic upgrade head`.
6. Run behind a trusted HTTPS reverse proxy using
   `uvicorn backend.main:app --host 127.0.0.1 --port 8080 --no-access-log`.
   The OIDC callback contains a short-lived authorization code in its URL;
   keep query strings redacted from reverse-proxy and platform access logs.
7. Open `/staff`, sign in with Workpeg, and verify the authorized department
   inbox. For guest access, a mapped receptionist issues and securely delivers
   a one-time invitation to a guest whose active stay they have verified.

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

Offline tests use synthetic hotel data, a mock OIDC identity result and an
isolated SQLite database. They verify route policy, guest-session scope,
idempotency, persistence across DB sessions, committed audit history,
department routing, privacy projection and failed-write rollback. They do not
verify Workpeg, an actual Workpeg OIDC client registration, PostgreSQL,
production deployment or message delivery.

Before an owner-authorized real development test:

1. Verify the Roomay Peg is installed in the exact development business and
   inspect `peg`, namespace, name and permission metadata for each required
   hotel table. This code requires Peg-owned tables; it will refuse peg-less
   tables rather than broadening permissions.
2. Configure OIDC redirect URI, client identity, approved server-side
   credentials and secret manager. Confirm staff membership claims in the
   provider's test account.
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

The existing owner-only Workpeg request/audit tables remain untouched and are
not this backend's source of truth. Decide and review their future migration
or deprecation before representing the system as a single unified Workpeg
database. Do not grant broader Workpeg permissions to make this backend run.
