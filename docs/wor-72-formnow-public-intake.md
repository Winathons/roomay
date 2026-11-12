# WOR-72 — formnow-style public booking-inquiry intake (isolated phase)

**Status: independent engineering phase only, not approved for deployment.**
ROOMAY's approved operational source of truth remains **Workpeg Tables**.
This phase is a temporary external staging queue, **not** a booking, active
stay, guest-service ticket, staff action, or an alternate hotel's database.
It does not start ROOMAY's disabled `backend.main` operational prototype.

## Verified reference and architecture choice

Workpeg's open-source [formnow](https://gitlab.com/workpeg/formnow) provides
[working source](https://gitlab.com/workpeg/formnow/-/blob/main/peg/ui/pages/forms.py)
and the [build-your-own guide](https://gitlab.com/workpeg/formnow/-/blob/main/docs/build-your-own.md).
A public user sends a form to an external server with no Workpeg Tables key.
The server holds a queued response. A signed-in Workpeg Peg **pulls** the
response in a lease, writes it to the owner's Workpeg table with `workpeg.add_row`,
checks the row, and **then** acknowledges it to the external server.
The Peg's server API identity is established with a Workpeg-registered OIDC
client and in-page `sso.approve`; OIDC is not Workpeg Tables permission.
formnow's collection runs on page open/manual sync, **not in the background**.

## What the scoped implementation does

- The `public_intake/` package contains an isolated SQLAlchemy queue, a
  FastAPI application **factory**, and a transport-independent async
  collector. There is **no production ASGI entrypoint**; `create_intake_app`
  refuses to initialize except with `test_mode=True` for isolated tests.
- Trusted `IntakePortal` bindings map an opaque public `portal_id` to a
  single Workpeg business and hotel. A guest cannot submit business/hotel
  identifiers in the request body or choose a staff scope.
- Public `POST /api/v1/public/portals/<portal_id>/booking-inquiries`
  validates dates, party size, contact email, explicitly affirmative consent,
  and a UUID idempotency key. It records **unverified booking interest**
  only and answers HTTP 202 with a non-sensitive receipt:
  `queued_pending_staff_collection`, `booking_confirmed: false`, and
  `workpeg_delivery_confirmed: false`. Replaying a matching idempotency key
  returns the same receipt; changed content gets HTTP 409.
- The temporary queue implements a database-backed limit of **20 per minute
  per portal/address**, using a keyed address digest rather than storing the
  raw client IP. Do not trust arbitrary `X-Forwarded-For` headers. This does
  not replace a production edge WAF or abuse protection.
- Staff-only `POST /api/v1/staff/inquiries/lease` requires a **server-injected
  verified identity**, currently owner-only under the canonical Workpeg
  table's `700` permission boundary. It scopes by business **and hotel**,
  leases up to 20 queued items at a time for 120 seconds, and sends a
  single-use lease token. The current implementation has no real OIDC
  resolver; unconfigured staff access fails closed.
- The generic `collect_batch` port accepts a future authenticated Peg
  `writer.find_by_source` / `writer.write_unconfirmed_inquiry` adapter.
  It **re-reads** the Workpeg row separately and checks business, hotel,
  source ID, payload digest, table UUID and native row ID before calling
  the queue acknowledgement endpoint. Failed/ambiguous writes or readbacks
  **must not be acknowledged**. A prior committed row can be recognized on
  retry without rewriting it.
- Staff `POST /api/v1/staff/inquiries/ack` verifies the owner/business/hotel,
  live lease token and exact claimed readback fields, records a minimal
  reference, and deletes staged email/note PII immediately. The external
  queue **cannot independently prove** the Workpeg readback: the future Peg
  is the trusted party and must not lie. A forged readback from an
  authenticated user is not cryptographically detectable by this server.
- Uncollected inquiries expire after **72 hours** and acknowledged minimal
  receipts after **24 hours**. `purge_expired()` must be run by an
  owner-managed scheduled job when deployment is later approved; no job
  is installed by this PR. Pending inquiries can be lost on expiration:
  retention, notifications, monitoring and guest disclosure need owner
  sign-off before live use.

## Data boundaries

| Data | Temporary server | Canonical Workpeg Tables |
| --- | --- | --- |
| Public booking interest / contact email | Held pending collection, purged | No row until verified Peg write |
| Unconfirmed public-inquiry draft | Future Peg integration only | A **separate owner-approved draft inquiry table**, not yet provisioned |
| Reservation, occupancy, stay, verified service ticket | **Never** committed by this package | Existing canonical hotel/request tables, under separate authorized workflows |
| Staff/Workpeg credential | Never held or minted by this queue | Remains only within Workpeg's signed-in Peg; external server holds eventual **OIDC client secret**, not a Tables key |

Do **not** import an anonymous booking inquiry directly into the current
`reservations`, `stays` or `Roomay Service Requests` tables: those have
verified guest/stay/permission requirements and different semantics. The
future draft-inquiry table needs an approved schema with at least
`source_id`, `business_id`, `hotel_id`, `payload_digest`, booking interest,
contact, a pending-review state and an audit/reconciliation policy.
No such table is created here.

## Tests and source verification

```
python -m unittest tests.test_public_intake -v
python -m unittest tests.test_public_intake_postgres -v
python -m unittest discover -s tests -v
python -m compileall -q public_intake tests
workpeg ui build ui/
```

`tests.test_public_intake` exercises HTTP submission/validation, tenant
scope, idempotency, rate limiting, owner authorization, expiry, leases,
unsafe readback, duplicate sync, lost ACK and PII scrubbing with synthetic
SQLite test state. When `ROOMAY_TEST_DATABASE_URL` is the existing
loopback-only PostgreSQL 16 CI service, a second suite creates **its own
random schema** and verifies `SKIP LOCKED` lease concurrency and durable ACK.
The tests never call Workpeg or outside services. The existing release gate
must continue to permit only read-only `/` and Reception routes; this new
service is not registered in `ui/main.py` or `workpeg.json`.

## Blockers before any live activation

1. **WOR-69:** Workpeg must register the actual ROOMAY OIDC client, exact
   public HTTPS callback and allowed scopes. formnow's API uses SDK
   `0.159.0`, whereas ROOMAY pins `0.152.0`; exact supported auth/`sso`
   calls must be checked in that environment. A fake test resolver must
   never be promoted into production.
2. **WOR-28/29:** Owner must verify real Workpeg role grants, authorized
   native writes, full independent readback and safe concurrency in the
   approved development business. The current `700` ACL stays unchanged.
3. **WOR-34:** Implement and verify the **actual compiled Workpeg staff UI
   collector** against a separately owner-approved draft-inquiry table;
   this PR provides only a tested orchestration port, not native UI wiring.
   The Workpeg row schema currently has no unique column guarantee, so
   repeated overlapping lease imports can still create duplicates; a
   safe serialized or idempotent workflow is required before live use.
4. **Privacy/operations:** Approve terms/consent copy, HTTPS production
   origin, anti-spam/WAF, persistent database migrations/backups, scheduled
   purge, staff queue monitoring and a manual fallback before publicly
   exposing the endpoint. Current code deliberately cannot boot publicly.
5. **Delivery:** An external booking inquiry being queued does **not**
   guarantee a staff member sees it immediately. Urgent housekeeping,
   Vapi verified-stay requests, human escalation, real-time status readback
   and a confirmed booking workflow still belong to WOR-65/69/11/13/22.

All production activation actions require separate, explicit owner approval.
No public Workpeg Function `/invoke`, `WORKPEG_PK` Tables credential, hidden
staff access or operational PostgreSQL alternate writer is inferred here.
