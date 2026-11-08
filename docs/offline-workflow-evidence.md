# Offline hotel workflow evidence (WOR-50)

This is deterministic regression evidence over fictional records and pure Roomay
domain functions. It is not an end-to-end Workpeg test. No Workpeg API, table,
credential, live hotel record, or persistence adapter is used by the new workflow
test. Test-only assignments apply returned plans to a copied Python snapshot so
subsequent domain functions can be exercised; this is not a production reducer,
transaction, or successful save.

## Workflow status

| Step | Status | What is exercised | What it does not prove |
|---|---|---|---|
| Guest reservation request | **PASS — offline plan only** | `prepare_booking_request` returns a pending reservation request with no room assignment or stay; repeating the same idempotency key is recognized. | The function does not authenticate a guest, submit a hosted request, or persist it. Guest-facing booking submission is not integrated. |
| Staff reservation confirmation | **PASS — offline plan only** | `prepare_authorized_room_confirmation` proposes the pending-to-confirmed transition when the supplied `WriteContext` passes. | Context booleans are claims, not Workpeg authorization or a concurrency lock. No reservation was saved. |
| Room eligibility | **PASS — pure domain rule** | Same-room eligibility, assignment conflict, date overlap, occupancy, room enablement, housekeeping readiness, and active maintenance blocks use `domain.hotel` rules. | An eligibility result is advisory and does not reserve inventory. |
| Authorized check-in | **PASS — offline plan only** | `prepare_check_in` requires confirmed assignment, valid occupants, trusted-clock claims, IANA hotel timezone, matching hotel-local operational date, and room readiness. | No trusted server clock, hosted staff authorization, or serialization guard was contacted or established. The test supplies these claims and patches the timezone lookup deterministically. |
| Physical stay creation | **PASS — test snapshot only** | The test copies the returned stay plan into its in-memory fixture, re-validates the complete hotel snapshot, and passes it to the canonical receptionist projection, which shows the room In house. On Nov 9, after its Nov 8 scheduled departure, the checked-in stay remains In house and is labeled OVERDUE, not checked out. | The plan is not persisted and is not an actual check-in. |
| Registered occupant association | **PASS — test snapshot only** | The stay guest references the intended guest; `validate_snapshot` and the offline guest-profile policy accept the active registered occupant. | The `AccessContext` and hotel mapping are synthetic, forgeable values; Workpeg role enforcement is not tested. |
| Guest service request | **PASS — offline command plan** | `create_request` verifies the guest against the active stay and creates a received plumbing request routed to Maintenance. | The request and its audit event are pending plans, not persisted records. Request text is synthetic. |
| Department routing and status transitions | **PASS — offline command plans** | The test routes to Maintenance and prepares Received → Assigned → Acknowledged → In Progress → Resolved. It checks each proposed audit event and uses test-local state for the next transition. | Test-local state is not the Workpeg write/reconciliation path. Events remain `pending`; no department permissions or audit persistence were verified. |
| Maintenance block | **PASS — pure eligibility rule** | The candidate room is eligible before a synthetic block is added and confirmation is refused after the active overlapping block is added. | No hosted block or reservation was created or changed. |
| Checkout and housekeeping handoff | **NOT IMPLEMENTED** | The schema and snapshot validator can represent and validate a checked-out stay and housekeeping state. | There is no checkout command or operational housekeeping handoff in the current domain API. This workflow is not simulated as a supported operation. |

## Adversarial regression coverage

The new cross-workflow suite is `tests/test_hotel_workflow.py`:

- `test_duplicate_and_overlapping_reservations_are_rejected_safely` covers
  idempotent repeated requests and a competing confirmation for the same room
  and dates.
- `test_room_occupancy_housekeeping_disabled_and_maintenance_gates` covers an
  occupied room, a dirty room at check-in, a disabled room, and a room that
  changes from eligible to blocked after a maintenance block is added.
- `test_stale_wrong_business_and_invalid_service_transitions_fail_closed`
  covers stale and unauthorized command context, wrong-business access, and an
  invalid Received-to-Resolved service transition.
- `test_guest_request_to_checked_in_guest_service_lifecycle` covers duplicate
  check-in attempts, legitimate active-occupant association, wrong-guest request
  access, and continued physical occupancy after the scheduled departure date.
- `test_check_in_plan_readback_is_not_a_persistence_claim` exercises the
  existing read-back classifier and confirms that its absent-row result remains
  a guarded retry classification, not a saved stay.

Existing focused suites continue to cover detailed validation and negative
cases in `tests/test_hotel.py`, `tests/test_reservation_commands.py`,
`tests/test_service_requests.py`, and `tests/test_access_control.py`. The
compiled UI test suites are mocked and forbid network access; they are not
hosted Workpeg workflow evidence.

`tests/test_workpeg_adapter.py::test_historical_request_room_is_rejected_when_current_stay_room_differs`
models a valid current hotel snapshot where the checked-in stay and its
reservation refer to a different valid room than a prior request's original
`room_id`. It verifies the current adapter rejects that snapshot as
`invalid_service_request`. The prior request remains unchanged. This is the
adapter's present fail-closed behavior, not a room-transfer implementation.

## Implementation gaps and hosted blockers

- **HOSTED BLOCKED — WOR-28:** The installed Peg/business namespace and
  authenticated development table CRUD/reload path have not been verified.
  Resolve namespace ownership/install access and complete an owner-run,
  synthetic-data Workpeg test before connecting hotel workflows.
- **HOSTED BLOCKED — authorization:** A trusted Workpeg session, server-derived
  staff/guest membership, business scope, and role/department grants must be
  verified on the server. Offline `WriteContext` and `AccessContext` values do
  not enforce access.
- **HOSTED BLOCKED — booking concurrency:** Workpeg SDK 0.149.1 has no verified
  transaction, uniqueness, compare-and-swap, or reservation serialization
  primitive in this integration. Competing confirmations must remain fail
  closed until a trusted concurrency-safe writer is proven.
- **HOSTED BLOCKED — check-in consistency:** A real writer must re-read current
  booking, room, stay, occupant, block, and authorization state; obtain the
  authoritative hotel-local clock/timezone; apply the stay and all occupant rows
  safely; and reconcile partial or timed-out results without blind retries.
- **NOT IMPLEMENTED — service persistence:** Request rows and audit events need
  an authorized adapter that persists and reads back both sides of each change,
  with idempotency, serialization, and manual reconciliation for partial writes.
- **NOT IMPLEMENTED — checkout and handoff:** Define and implement an authorized
  checkout operation, occupant departure/audit treatment, and housekeeping handoff
  before claiming this workflow.
- **NOT IMPLEMENTED — room transfers (WOR-12):** The current adapter requires a
  request's historical `room_id` to equal the stay's current room and therefore
  fails closed after a hypothetical room change. Do not rewrite old request
  records or weaken this check. A trusted, authorized room-transfer contract
  with an auditable room-history association is required before legitimate
  transfers can be supported.
- Guest reservation submission, guest channel identity, and hosted cross-guest /
  cross-department denial require separate authenticated UI and Workpeg tests.

## Required Workpeg-backed verification after WOR-28

An authorized owner must run these checks only in the confirmed Roomay AI
development business with fictional records:

1. Resolve the registered Peg namespace and owning business, install/access it
   through the supported Workpeg development process, and prove an authenticated
   table read/write/reload smoke test with no developer token in browser code.
2. Verify table identities, row schemas, business scoping, owner-only baseline
   permissions, and explicit denied access for ungranted staff and guests.
3. Connect the existing `domain/workpeg_adapter.py` contract; read authoritative
   rooms, guests, reservations, stays, blocks, requests, and audit rows. Verify
   that malformed, cross-business, and incomplete snapshots fail closed.
4. Verify guest and staff identity from Workpeg, never browser-supplied roles or
   business IDs. Exercise wrong guest, wrong department, nonmember, and
   cross-business denials on hosted data.
5. Demonstrate a real reservation request read back after refresh. Before
   enabling confirmation, prove the server-side serialization/uniqueness method
   under two competing attempts; otherwise keep confirmation pending/refused.
6. Demonstrate check-in read-back for the stay and every registered occupant,
   using an authoritative hotel timezone/clock, plus partial-write and timeout
   reconciliation. Confirm the room remains physically occupied until explicit
   checkout, regardless of scheduled departure.
7. Persist a guest request and each department transition with corresponding
   audit events; test duplicate submission, failed writes, cross-guest access,
   and fresh-session/reload behavior.
8. Implement and separately verify checkout/housekeeping handoff before marking
   that step complete. Do not mark WOR-23 done from this offline evidence.

No hosted verification, table provisioning, customer data, or Workpeg permission
change was performed for WOR-50.
