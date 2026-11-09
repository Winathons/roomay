# Reception read integration and offline acceptance

## Current behavior

The authenticated receptionist route reads the nine canonical Workpeg tables
from the business in the route context. It paginates row reads, validates
business IDs, native row IDs and fingerprints, validates table contracts and
relationships, and fails closed if any required page or record is missing,
ambiguous or malformed. It does not substitute fixtures when Workpeg reads
fail. The route remains read-only and the tables remain permission `700`.

The receptionist projection now keeps the reservation, physical stay and
registered occupants distinct. For an active stay it displays the registered
occupant names; reservation booker information is not treated as proof of
occupancy. Room cards expose reservation and stay statuses separately. The
request list includes its associated room and guest plus a sanitized audit
timeline. Audit fields that could expose internal IDs, operation signatures or
free-text reasons are omitted. Audit state is described as pending or marked
committed only; neither label implies staff notification, delivery or completed
work.

The owner reports having verified the Roomay AI development business contains
the complete fictional Room 205 / extra-towels workflow. This change does not
re-read that hosted inventory. Run the owner-only browser acceptance below to
verify that the current UI displays it. Offline fixtures prove projection and
contract behavior only; they do not prove current hosted records or staff
access.

## One-command offline acceptance

From the repository root, run:

```powershell
.\.venv\Scripts\python.exe tests\run_reception_acceptance.py
```

The runner aggregates the adapter, schema migration, synthetic vertical-slice,
compiled UI controller, reception projection and release-candidate suites into
one final `RECEPTION ACCEPTANCE: PASS/FAIL` line. These tests use synthetic
Workpeg response envelopes and block network access in the compiled controller
harness. They cover canonical contracts, pagination, invalid/duplicate rows,
wrong business and permission, auth-denied UI states, stale fingerprints,
uncertain writes, partial request/audit completion, projection consistency,
privacy boundaries and release-route exclusions. The runner performs no
Workpeg calls and no writes.

## Development test-data orchestration

Do not create a second orchestrator or data store. The existing
`domain/vertical_slice.py` planner and isolated `ui/dev_vertical_slice.py`
procedure are the bounded WOR-60 test-data path. The planner is deterministic,
preserves the existing `room_types` row, detects unexpected inventory and
prepares only the next row in sequence. The development UI is excluded from the
production router and requires per-operation operator confirmation.

For a future owner-reviewed usability improvement, confirmations may be
reduced to one explicit approval of a displayed immutable plan (business,
namespace, exact row sequence and all payloads). That approval must remain
separate from authenticated Workpeg authorization; rows must still be written
sequentially, each read back before continuing, with a stop on any timeout,
partial result, mismatch or ambiguous outcome. No automatic retry, rollback,
delete or bulk write is safe while Workpeg does not provide a verified atomic
multi-row transaction or compare-and-swap guarantee. This task does not change
the live-write UI or execute the planner against hosted data.

## Owner-only read acceptance

After reviewing this change, an authorized owner can open the authenticated
Roomay AI business and navigate to `/b/{business_id}/reception`. Use **Refresh
records**. A successful read should show Room 205 as occupied by the registered
fictional guest, its confirmed reservation and checked-in stay, housekeeping
state, the received extra-towels request routed to Housekeeping, and the audit
event. The request/audit view must not imply delivery or acknowledgement.
Capture only sanitized evidence. If any table is unreadable, the UI must show an
error and no fixture fallback. This read acceptance is not a staff-permission
test and does not authorize writes.

## Requirements before real guest request operations

The current tables are owner-only (`700`). Their existence and the owner's
successful test do not show that Housekeeping or other staff can read or update
them. Before enabling guest request submission or a department inbox:

1. Obtain a reviewed Workpeg permission design for each table and business
   role. Verify allowed and denied operations using separate authorized test
   accounts. Do not infer authorization from browser-supplied role claims.
2. Establish a trusted guest session using the WOR-15 identity contract.
   Room number, QR code, caller ID and model output are not identity proof.
3. Expose a narrow server-side action gateway. It must derive business, hotel,
   guest, room, stay, actor and department scope from trusted records, then
   invoke existing `domain/service_requests.py` authorization and transition
   rules. Typed chat and Vapi must call the same validated action.
4. Add idempotent request creation, trusted serialization/concurrency control,
   durable request plus audit handling and read-after-write reconciliation.
   Workpeg's current documented row helpers do not establish an atomic
   request-and-audit transaction or conditional update. Partial/uncertain
   writes must stop for reconciliation; they must not be represented as
   submitted.
5. Build a department-scoped inbox and status response path. Verify that each
   department can see only its requests, can perform only permitted lifecycle
   transitions, and cannot read unrelated guest data. Validate audit persistence
   independently; a row in an audit table is not proof of notification or work.
6. Exercise the entire typed-chat and voice path with owner-approved synthetic
   records, including denied access, duplicate requests, timeout reconciliation,
   authorized acknowledgement, status reload and guest-visible privacy.

Until those hosted permission, identity, serialization and persistence checks
pass, the receptionist remains read-only and guest chat/voice cannot claim a
request was submitted, delivered, acknowledged or resolved.
