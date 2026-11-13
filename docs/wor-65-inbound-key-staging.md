# WOR-65 — Inbound Key staging transport proposal

**State: optional offline implementation; disabled and not authorized for live use.**

Workpeg's published Tables documentation describes a server-only Inbound Key API: `GET https://api.workpeg.com/v1/inbound/whoami/` returns the key's business and table, and `POST /v1/inbound/rows/` creates one row in that bound table. The write body is exactly `{"data": {...}}`. `Idempotency-Key` accepts 1–100 printable characters; a first write returns 201, a duplicate returns 200 without adding a row, and a concurrent in-progress key returns 409 with `Retry-After`. The API documents 401 for invalid/revoked keys, 403 for unusable permissions/scope, 422 for a rejected pre-save hook, 429 for throttling, and 503 for hook failure. Requests carrying an `Origin` header are refused.

`domain.workpeg_inbound.WorkpegInboundTransport` encodes this contract for trusted-server use only. It defaults disabled, has no credential/env bootstrap, does not attach a browser Origin, blocks redirects, verifies `whoami` matches configured business and table before each write, derives one stable printable idempotency key per queue source ID, and returns only a staging receipt. It enforces Workpeg's 256 KiB body limit. A 200 duplicate and 201 first insert both mean staging persistence only. A 409 is still in progress; 429 is not written; timeouts and 503 are outcome-unknown. These cases expose a bounded numeric `Retry-After` when supplied. Callers must retry with the same key and honor the delay; this adapter does not retry automatically. Authorization failures are terminal until configuration/permission is corrected. Error values omit response bodies and credentials.

## State boundary

These are distinct facts:

1. `external_queue_accepted`: the guest intake queue accepted an item (WOR-72).
2. `workpeg_staging_persisted`: an Inbound Key created or replayed a staging row. This says nothing about Workpeg staff visibility or acknowledgement.
3. `operational_request_committed`: the authorized WOR-65 workflow wrote the canonical service request and its audit event and reconciled both.
4. `staff_acknowledged`: an authorized staff member explicitly acknowledged the operational request in the staff workflow.

The transport reports only state 2 and marks states 3 and 4 `not_asserted`; it has no authority to set them. It is not wired to the current public APIs, Vapi, the WOR-72 collector, or the canonical writer. Existing stay verification, actor authorization, request/audit reconciliation, and guest readback contracts remain in force.

## Staging table proposal

If Workpeg approves enabling this path, provision a **separate Peg-owned staging table**, not `Roomay Service Requests`, `service_requests`, or the canonical audit table. Proposed minimum columns are `source_id` (stable queue UUID), `source_kind`, `business_id`, `hotel_id`, `payload_digest`, `received_at`, `category`, `department`, `urgency`, bounded `description`, and a fixed `review_state` of `pending_review`. Include guest/stay/room identifiers only if the approved review workflow needs them and has an approved privacy boundary. Inbound-created rows must not contain fields that assert `operational_request_committed` or `staff_acknowledged`; those facts remain in the canonical request/audit lifecycle. A human-authorized Workpeg workflow must validate the verified stay, guest, consent and routing, then use the existing WOR-65 canonical request/audit writer and its reconciliation checks. A staging row must never become a staff ticket solely by existing.

The table schema, permission/ACL, key scope, key owner and lifecycle, data retention, hook behavior, staff review UX, and promotion protocol require separate Workpeg/ROOMAY owner approval. Workpeg documents that the key is created by a table writer from the Peg's own page only after the `inbound` scope is declared and granted; the key cannot read rows or promote a staging row. This code creates no table/key, changes no scope or manifest, and makes no live calls.

## Relationship to the tracked work

- **WOR-72:** remains the guest-facing external queue and its independent idempotency, leases, expiry, PII purge and acknowledgement boundary. This transport does not replace or duplicate that queue. Until an approved adapter coordinates queue leases and inbound writes, do not run both paths for the same item.
- **WOR-65:** remains blocked on supported guest-to-staff identity and authorization, verified stay/occupant, canonical request plus audit persistence/reconciliation, staff visibility/authorization, and guest status readback. Inbound row creation satisfies none of those gates.
- **WOR-69:** Workpeg's official registration/integration decisions still govern external guest/Vapi ingress and OIDC. An Inbound Key is a narrowly scoped write credential, not guest identity, OIDC, a Tables read credential, or an authorization bridge. The key's creation/activation and approved destination remain owner/vendor gated.

## Offline verification

`python -m unittest tests.test_workpeg_inbound -v` uses mocked HTTP responses only. No Workpeg request, inbound scope activation, credential, manifest, permission, table, or hosted data is involved.
