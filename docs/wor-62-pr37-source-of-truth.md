# WOR-62 — Approved request/audit source of truth (Option A)

**Architecture decision: APPROVED by the project owner on 12 November 2026.**
**Implementation feasibility: BLOCKED pending Workpeg's supported external invocation/access contract.**
**PR #37 disposition: eligible for an *inactive infrastructure-only* merge, not a live integration release.**

## Decision

**Workpeg Tables are ROOMAY's canonical operational store for hotel service requests and their audit history.** Reception and department interfaces must operate on the **same canonical request IDs, statuses and committed audit events**. A guest request is not successfully delivered to hotel staff merely because a standalone FastAPI service has inserted rows in its own database.

The owner selected Option A rather than PostgreSQL as the hotel's request source of truth. The selected design **does not assert** that Workpeg currently exposes a supported external authenticated writer, or that request/audit writes are atomic. Those are explicit engineering/vendor acceptance gates.

## Intended architecture and responsibilities

1. **Hotel/stay identity:** use a Workpeg-authorized, business/hotel-scoped source. A verified active stay and registered occupant—not a room number, QR string, caller ID or AI output—must authorize guest-specific service requests.
2. **Single operational writer:** only a Workpeg-approved, authenticated, least-privilege path may commit a canonical service request and linked audit event. It must validate actor, business, hotel, stay, department and consent; handle idempotency and retry ambiguity without duplicate tickets. **No direct external `WORKPEG_PK` Tables call is authorized.** A Workpeg Function's invocation-scoped `context["token"]` must never be exported to or reused by an external server.
3. **Staff inbox:** the existing Workpeg Reception and department interfaces read the authoritative Workpeg request/audit tables. An unconfirmed guest request cannot be shown as `sent` or `received by staff`. Staff transitions must be authorized, preserve department scope and commit/read back the same record and audit ledger.
4. **Guest status:** the guest sees a projection of only their current or permissible historical stay requests via a supported authenticated read/bridge, with true committed status on a separate refresh. A Workpeg-side change cannot be inferred from a PostgreSQL-only change.
5. **Uncertain writes:** the approved integration must define what happens if one of request/audit commits, notifications or readbacks fails. A post-save hook alone does not prove atomicity or delivery. Until true transaction/serialization or a durable reconciliation protocol is verified, fail closed and require review rather than reporting false success.
6. **Least privilege:** existing owner-only `700` Workpeg table permissions remain unchanged until actual authorized staff roles/ACLs are approved and tested. We do not widen permissions merely to make the demo pass.

## Retained PostgreSQL code in PR #37

The FastAPI/PostgreSQL/Alembic implementation is preserved in the repository **only as a dormant, isolated engineering prototype**. It can verify relational transactions, idempotency, audit ordering and staff/guest authorization contracts in local tests. It is **not ROOMAY's approved operational request writer**; no dual-write, reverse proxy, synchronization or automatically accepted staff projection exists.

The standalone `backend.main` ASGI entrypoint now refuses startup by default. A deliberate **`ROOMAY_ENABLE_STANDALONE_PROTOTYPE=local-only`** setting is required merely to run it in an isolated developer environment; this flag **is not production authorization**. Even when set, the default hotel snapshot adapter fails with sanitized `503 hotel_records_unavailable`. No supported public Workpeg Function invocation, OIDC registration, hotel read, staff write, or real guest notification is implied. Production deployment/public ingress is forbidden until a separate reviewed integration gate is approved.

The source tree's existing FastAPI request-confirm endpoints can still write to PostgreSQL when directly exercised with injected synthetic hotel-reader fixtures in tests. Those writes remain **non-authoritative test records** and may never be presented as delivered to the real Workpeg receptionist.

**A later move to PostgreSQL as the operational request store (Option B) would require a new explicit owner decision**, plus a secure staff-facing replacement/projection, history reconciliation, real OIDC and guaranteed removal of competing Workpeg writers. Option B is not approved as a silent fallback to a Workpeg vendor refusal.

## Vendor confirmation and live acceptance outstanding

The owner has already received a Workpeg clarification that developer `WORKPEG_PK` is **not** a general standalone Tables credential. The supported authenticated *external* guest/Vapi → Function or Tables invocation method has **not** been established. Workpeg OIDC requires official client registration and proves identity, not Tables permission. These are blocking dependencies, not documentation-only tasks.

Before any live activation, independently verify in an owner-authorized test business:

- One guest attached to a verified checked-in stay explicitly confirms a service request.
- Exactly one canonical **Workpeg request and linked committed audit** are produced; a second confirmation/retry cannot duplicate the operation.
- A separately authenticated Reception user sees the request, a correctly authorized department user updates it, and the guest sees the same status on an independent reload.
- Wrong business/hotel/guest/department, expired session, revoked stay, room move, checkout, audit failure and unavailable Workpeg reject safely without leaking guest data or claiming delivery.
- Capture sanitized request/operation IDs and readback evidence; no credentials or real guest PII in PR, Linear or test logs.

**While blocked:** existing staff can take requests manually using an *actually authorized Workpeg interface* only when its permissions, persistence and audit have been validated. Do not claim the external guest portal or voice tool submitted a ticket.

## Merge, release and issue-state separation

After GitHub CI and review gates are green, the project owner authorizes **merging PR #37 into protected `main` as inactive infrastructure**, with no backend deployment, OIDC registration, Workpeg table edit, permissions expansion, public guest operation or auto-migration. No service is started by GitHub CI or the compiled Workpeg UI.

**WOR-61, WOR-62 and WOR-65 remain In Progress/blocked until the hosted integration is verified.** WOR-15's live guest safety acceptance is likewise incomplete. PR merge is a source-control milestone, *not* a declaration that a real guest request can reach staff.
