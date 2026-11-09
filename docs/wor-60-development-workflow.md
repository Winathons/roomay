# WOR-60 — synthetic hotel-to-service-request workflow

## Purpose and boundaries

This is an isolated owner-operated development procedure, not a production
feature or public guest workflow. The source is `ui/dev_vertical_slice.py` and
is compiled as a standalone Workpeg UI. It is not imported into
`ui/main.py`, and the release router remains limited to `/` and
`/b/[business_id]/reception`.

The owner reports that all nine tables exist in the Roomay AI development
business and that the existing `room_types` row has been persisted and
verified. This implementation made **no** Workpeg calls. It will read every
namespace, table and paginated row before proposing an operation. It refuses
to proceed if it sees an unreadable/missing table, schema or permission
mismatch, unexpected table or row, duplicate identity/fingerprint, malformed
page, cross-business row, room block, or a partial/out-of-order sequence.
`room_types` is read-only: its existing Roomay TEST row is neither inserted,
updated nor deleted.

Typed attestations and confirmations are workflow safeguards. They do not
prove the operator's Workpeg identity or owner role. Table and row permission
700 and absence of row-level grants must be verified by the owner in Workpeg
before each write. The request's `hotel_id` is a deterministic fictional
application identity required by the existing service-request contract; it is
not a verified Workpeg hotel mapping. The hotel schema has no `hotel_id`, so
this dataset demonstrates the documented single-hotel-per-business scope only.

## Proposed fictional rows

The exact request-time values depend on the owner-entered current hotel-local
date, time and IANA zone. The planner makes arrival that local date, departure
two days later, and uses the supplied local wall time for the check-in instant.
The Workpeg `dates` capability converts it to an explicit UTC offset. The
development controller currently accepts `Africa/Lagos`; unknown time zones
are refused instead of silently falling back to the browser or machine clock.

| Table | Fictional row |
|---|---|
| Existing `room_types` | Preserve `Roomay TEST Room Type (Fictional)`, capacity 3, using its live `entity_id` from the read. |
| `rooms` | Room 205, references the preserved room type, enabled, housekeeping `ready`. |
| `guests` | `WOR-60 Fictional Guest (Synthetic)`. |
| `reservations` | One assigned, confirmed, one-person advance reservation for Room 205. |
| `stays` | One `checked_in` physical stay, separate from the reservation. |
| `stay_guests` | The fictional guest registered to that stay. |
| `Roomay Service Requests` | Extra towels, Housekeeping, normal urgency, `received`, synthetic reception origin. |
| `Roomay Service Request Audit` | Matching `created` event, sequence 1, `pending` commit state, and matching request ID/event ID. |

Room, guest, reservation, stay, occupant, request and event UUIDs are stable
deterministic synthetic IDs. The request's idempotency key is
`wor60-extra-towels-v1`. These identities help detect duplicates; Workpeg does
not enforce uniqueness or relationships as foreign keys.

## Manual procedure after PR review and separate owner authorization

1. Confirm the approved `roomay` Peg is installed for the intended Roomay AI
   development business, sign in as the owner, and open the standalone
   development route `/b/<business-id>/dev-vertical-slice`.
2. Confirm the route business UUID with the Workpeg business context. Enter
   the exact UUID and owner attestation. In Workpeg, verify all nine table
   schemas and permission `700`, and inspect that there are no row-level grants.
   Enter the row permission attestation. The UI cannot prove the role; it only
   refuses to operate without owner acknowledgement.
3. Enter the current hotel-local date, the IANA zone `Africa/Lagos`, and a
   current hotel-local wall timestamp. Do not use the browser clock as an
   authority. **Before the first approved row write, record the exact approved
   date, IANA zone and wall timestamp privately and reuse those identical
   values on every page reload for this entire seven-row plan.** They determine
   check-in, request and audit instants; changing the time mid-sequence changes
   expected records and will correctly stop partial-row reconciliation.
   Never fabricate a new "current" time to bypass that stop. If the operator
   crosses a hotel-local day boundary before the plan is complete, stop and
   review the time/business rules instead of changing existing rows or
   relabeling the old stay as current. The offline domain tests inject a
   deterministic IANA zone because this Windows environment lacks a system
   tz database; the compiled UI uses Workpeg's documented `dates` capability.
4. Choose **Inspect all nine schemas and complete row inventories**. Confirm
   that the existing room type appears exactly once and remains capacity 3.
   Review every table row count and any failure. An empty list is only the
   readable inventory, not proof an inaccessible row does not exist.
5. Choose **Prepare exactly the next row**. Review the exact payload and
   dependency state. Type `CREATE ONE WOR60 ROW: <table-key>`, acknowledge the
   SDK's protected-helper refresh/retry behavior after 401/403, and attest that
   all earlier write outcomes have been reconciled. This test UI offers only
   one-row insertion: no batch, deletion, rollback, update, or table creation.
6. After a successful row, verify its Workpeg create response, native row ID,
   fingerprint, direct `get_row`, and complete fresh namespace/table/row read.
   Then reload the page, inspect again, and verify the persisted prefix before
   preparing another row. This prevents continuing from only browser-local
   state.
7. The sequence is room → guest → reservation → stay → registered occupant.
   After the five hotel rows have been independently verified after reload,
   enter `I RELOADED AND VERIFIED THE ACTIVE STAY`. Only then can the UI
   prepare the service request, followed by its audit row. Neither operation
   delivers a message to staff. The request remains `received`; no notification,
   acknowledgement, assignment or resolution is claimed.
8. After any timeout, denial, malformed response or mismatch, the screen locks
   the session against further writes. Do not retry. Inspect Workpeg as owner,
   reconcile actual rows and native IDs/fingerprints, then use a new page only
   after the outcome is known. Never delete or overwrite a row to recover.
9. Reload after the final audit record and inspect all nine tables again. The
   existing read-only receptionist adapter should validate a complete result;
   its production route remains read-only and does not expose this planner.

The SDK 0.152.0 authenticated helper may refresh/retry after 401/403. No
per-call switch disabling that behavior has been verified. Before any actual
write, the owner must acknowledge this caveat and treat a timeout as uncertain.
One-at-a-time UI calls do not provide server-side serialization or a database
transaction. A concurrent writer could still race; owner-controlled use in one
tab is an operational precaution, not atomicity.

## Partial completion and operational prerequisites

The UI resumes only when current rows are an exact ordered prefix of its
deterministic plan. Any different or out-of-order content stops the flow for
manual reconciliation. It performs no compensating delete. If a stay row is
present without its occupant, or a request without its audit row, do not claim a
complete operation or retry automatically. Re-read every affected row, record
sanitized native identity/fingerprint evidence, and ask the owner to decide the
recovery.

Before any real department use, Roomay still needs verified server-side staff
authentication, authorization and row grants; a trusted business-to-hotel
mapping; durable idempotency and concurrency control; a transaction or reviewed
reconciliation protocol for multi-row operations; audited staff attribution;
and an actual department inbox/notification flow. Workpeg table persistence of
the owner-only test rows would not prove those capabilities. Guest chat, Vapi,
and YarnGPT are not connected by this work.
