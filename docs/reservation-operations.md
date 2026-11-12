# Roomay reservation lifecycle — authoritative write contract

This document defines **real product business rules**, not a customer-facing sample application. It accompanies WOR-9. The module `domain/reservation_commands.py` prepares deterministic booking and confirmation decisions; it deliberately **does not make Workpeg writes** until platform namespace authentication, server-side authorization, and race-safe persistence have been validated.

## One business, one source of truth

Roomay uses Workpeg business-scoped tables as the system of record. A reservation request, a confirmed booking and a checked-in stay are **three distinct states**.

- **Request:** `pending_confirmation`. It neither claims a room nor changes physical occupancy.
- **Confirmation:** `confirmed`, with a valid room assignment and dates. This must follow an authoritative, serialized inventory check.
- **Stay:** a separate `stays` row created **only when authorized reception actually checks the guest in**. Confirmation alone does not create occupancy.
- **Cancellation:** updates a reservation's status but must not erase a reservation already used by a stay; staff need a dedicated checkout/change process for active guests.

Room availability must consider confirmed reservations, current physical occupancy, housekeeping readiness at check-in, active maintenance blocks, hotel-local dates and room-type capacity. Date intervals are half-open: `[arrival, departure)`, so a checkout on November 15 may be followed by a new arrival on November 15 **only after the physical guest has checked out and housekeeping clears the room**.

## What the code now does

- `prepare_booking_request(...)` validates a complete, single-business snapshot and immutable request fields. It creates an uncommitted `pending_confirmation` record, with a deterministic request ID derived from an opaque idempotency key. Retries with the same key can be recognized by a subsequent complete snapshot.
- `prepare_room_confirmation(...)` evaluates a **pending** booking against an eligible room and requires a caller-supplied assertion that an authorized staff review occurred. A proposed assignment is not a confirmed booking.
- `prepare_cancellation(...)` refuses to cancel bookings already associated with a stay; cancellation of a pending/confirmed booking is otherwise a proposed operation requiring a trusted write.

Every returned `ReservationPlan` is explicitly `persisted=False` and `requires_authoritative_guard=True`. This is intentional. The code is the platform-independent **validation core**, not a bypass for Workpeg authentication.

### A successful local eligibility result is NOT a reservation guarantee

Two receptionists can read the same available Room 204 at the same time, both receive valid local plans, and race to confirm it. The second decision is only safe **after** the first writes and the updated authoritative state is observed.

To prevent this conflict in the actual hotel product, we need a **server-enforced atomic/serialized write path** or a proven equivalent Workpeg concurrency mechanism that rejects the second confirmation. A browser-side double-check is insufficient. If Workpeg cannot guarantee this, keep requests **Pending Confirmation**, limit confirmation to a controlled human workflow and explicitly record that no instant guarantee is available. Do not claim the human workflow itself is atomic.

The deterministic request ID helps retry reconciliation but is **not** a uniqueness guarantee until Workpeg confirms/enforces the relevant row constraints. It is an opaque key, not a guest phone number, room number, payment ID, or sensitive personal data.

## Workpeg platform constraints / security

- Workpeg's UI table helpers operate using the signed-in business staff session. Verify the staff role and table write permissions on the **server**, not via `staff_authorized=True` supplied from a browser.
- The table platform supports pre- and post-save hooks. **Post-save hooks cannot reject a completed write**. A custom pre-save hook may require a published/installed Function; verify the supported enforcement path before routing sensitive confirmation actions.
- The Workpeg hooks documentation currently warns that **pre-save hooks do not run for declarative agent writes**. Therefore AI must **not** receive direct, unguarded reservation-confirm or room-safety write actions. AI can collect pending requests and hand them to an authorized and checked staff workflow.
- Writes may succeed even if the browser times out. After uncertainty, read back by the same stable identifier before retrying; don't create a second room assignment blindly.
- Make business tenant scoping explicit; no cross-business customer or occupancy records.
- Check-in/checkout, occupant registration, payments and room change have separate workflows and need additional authorization and atomicity design (WOR-11/WOR-12).

Official SDK references:
- https://developers.workpeg.com/docs/latest/tables/
- https://developers.workpeg.com/docs/latest/hooks/
- https://developers.workpeg.com/docs/latest/manifest/

## Operational integration checklist

1. Historical blocker superseded: the owner reports that authenticated access and persistence for the existing development `room_types` table have now been verified. WOR-28 remains open for role permissions and the remaining hosted integration criteria; do not treat the former HTTP 400 namespace error as current status.
2. Verify table/schema and owner role permissions, plus any real support for atomic confirmation or a serialized trusted gateway under **WOR-29** and **WOR-22**. Do not invent platform guarantees.
3. Adapt the pure plans to an actual, authenticated Workpeg reservation service. Fetch a **complete fresh** snapshot, authorize the actor, recheck constraints at commit time, perform the guarded state transition and verify the actual persisted record.
4. Register the actual read-only booking request and staff confirmation experiences under business-scoped routes, not the temporary fixture route. Show honest pending/confirmed status and error/recovery.
5. Test competing browser sessions, retried writes, invalid date intervals, unauthorized roles, late checkout/housekeeping changes, cancelled bookings, room blocks and cross-business denial.
6. Demonstrate complete Workpeg read/write/refresh under a development business before closing WOR-9 or promoting a release.

## Test scope

`tests/test_reservation_commands.py` covers requests, deterministic retries, duplicate-key payload conflicts, invalid party sizes/dates, unauthorized actions, confirmed room conflicts, cancellation of used bookings, and competing confirmation plans. CI tests validate **business logic**, not hosted Workpeg storage or role enforcement.
