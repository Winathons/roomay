# WOR-11 write gates: reservation confirmation and physical check-in

This Phase A contract prepares offline intents only. `ReservationPlan` and
`CheckInPlan` always have `persisted=False`; neither is a booking, confirmed
reservation, occupied room, or completed check-in. A walk-in starts as a
`pending_confirmation` reservation request with no room assignment and no stay.
Confirmation assigns a room to the reservation. Physical arrival is a separate
stay row plus one or more registered occupant rows.

## Offline commands now available

- `prepare_walk_in_request(...)` delegates to the established booking-request
  validation and requires a fresh business-scoped context plus serialized
  idempotency guard. The request stays pending and creates neither room
  assignment nor stay.
- `prepare_authorized_room_confirmation(...)` requires a fresh snapshot,
  matching business identity, authorized reception/management/owner, and a
  server-held serialization guard. It reuses existing room eligibility checks.
- `prepare_check_in(...)` requires the same gate, a confirmed assigned
  reservation, check-in date in the booking interval, a ready and unoccupied
  room, no overlapping maintenance block, valid occupants within party size,
  and an offset-bearing timestamp. It also requires an explicit IANA
  `hotel_timezone`, converts the timestamp instant into that zone, and rejects
  when its local date differs from the date derived from the trusted
  `WriteContext.authoritative_now`. The supplied operational date must match
  that derived date, and a future check-in timestamp is rejected. The input
  timestamp's own offset does not identify the hotel's time zone. It returns
  deterministic stay and occupant records, separately from the reservation.
- `reconcile_check_in_readback(...)` classifies a complete post-timeout read.
  Matching rows mean the expected rows were observed and must not be repeated;
  absent rows permit a retry only while a guard is held; partial/malformed or
  conflicting rows require manual reconciliation. It does not claim a
  transaction committed.

The `WriteContext` fields, including `authoritative_now`, are a contract between
a future trusted server-side adapter and this pure logic. The adapter must
source `authoritative_now` from its trusted clock, not a browser clock.
Constructing a `WriteContext` in a browser or
offline test does not authenticate a user, validate Workpeg permissions, make a
snapshot fresh, or create a lock. Never accept those claims directly from an
untrusted client. The current Workpeg UI adapter has no verified concurrency
mechanism, so it must not call these write paths in production.

## Required future Workpeg sequence

1. Resolve the Workpeg namespace/installation issue and establish the exact
   authenticated business context from the Workpeg staff session. Verify the
   requested business ID against the session on a trusted server boundary.
   Resolve the hotel's IANA time-zone identifier from authoritative hotel
   configuration. Never derive it from the browser clock or timestamp offset;
   if configuration or time-zone data is unavailable, refuse check-in.
2. Authorize the actor and operation server-side using the current business
   membership/role. Guest access may submit a pending request only; guests may
   not assign rooms, confirm reservations, or check themselves in. Restrict
   confirmation/check-in to authorized reception, management, or owner roles.
3. Acquire a server-enforced per-business inventory/booking serialization
   mechanism that remains held for the complete read-check-write-read sequence.
   A browser mutex, stale marker, row fingerprint, idempotency UUID, or
   Workpeg `update_row` call is not that mechanism.
4. Under the guard, read every required table page and validate the complete
   snapshot. Refuse missing pages/tables, malformed records, changed business
   identity, stale state, dirty/occupied/blocked rooms, existing stays,
   overlapping confirmed bookings, invalid booking dates, and duplicate keys.
5. For a walk-in, create only a deterministic pending request. Enforce
   idempotency on the trusted writer or a platform uniqueness primitive; read
   back the stable ID after an uncertain write. Do not assign a room or create a
   stay at this stage.
6. For confirmation, recheck eligibility while holding the guard, then write
   the complete reservation row with assigned room and `confirmed` status.
   Preserve all unrelated data because Workpeg row `PATCH` replaces the entire
   nested `data` object even when the outer request is PATCH. Read back the row
   and validate its business, identity, assignment, dates, and status before
   reporting confirmation.
7. For physical check-in, repeat authorization and room/stay eligibility under
   the guard. Add the stay and registered occupant rows using their stable
   deterministic IDs. Since these are multiple row writes without a documented
   transaction, do not show successful check-in until all rows are read back
   and the complete domain snapshot validates. On partial success, stop and
   require explicit reconciliation; do not blindly retry or free occupancy.
8. Keep the guard through reconciliation, release it only after an authoritative
   final read, and emit an actor/audit record as required by the hotel's
   approved audit contract.

## Current platform blocker and required verification

The pinned Workpeg SDK 0.149.1 and current official Tables & Rows documentation
expose table/row CRUD and row fingerprints. They do not document a transaction,
unique constraint, conditional update, compare-and-swap, or a lock helper. A
fingerprint is a change marker, not a write precondition. Therefore there is no
verified way in the current UI adapter to guarantee concurrent confirmation or
multi-row atomic check-in. The user interface must keep these operations
disabled until an approved trusted writer or documented platform primitive
proves the gates above.

The pinned Windows virtual environment also has no IANA time-zone database
(`tzdata` is absent and Windows does not provide the database through Python's
`zoneinfo` lookup). `prepare_check_in` therefore refuses with
`authoritative_hotel_timezone_unavailable` in that environment unless a valid
IANA zone database is supplied by the eventual runtime. The tests inject a
deterministic fixture zone to exercise date-boundary behavior; this is not
hosted time-zone verification.

Before enabling real writes, an authorized owner must verify in the isolated
Roomay development business: installed Peg and authenticated role context;
same-business denial; server-side role enforcement; the actual serialization
mechanism under two simultaneous staff attempts; full-row PATCH preservation;
write timeout reconciliation; partial stay/occupant recovery; refresh and
reload; and audit attribution. No live Workpeg calls, provisioning, credentials,
or hosted verification were performed for this phase.
