# WOR-12 — guarded in-house room transfer (offline implementation)

The existing checkout and housekeeping plans (`domain/checkout_commands.py`) already cover:
- Checkout ends the active stay and registered occupants, makes **the actual occupied room dirty**, and rejects duplicate checkout.
- Housekeeping transitions dirty → cleaning → inspection → ready with supervisor approval and maintenance-safety evidence.
- All plans are **unpersisted**; real Workpeg actor verification, transaction/serialization, durable idempotency and readback are still required.

## New transfer contract

`domain/room_transfer.py` proposes a same-stay, same-room-type physical transfer, restricted to verified reception/management/owner context. It requires a fresh and complete safety/request snapshot, an authoritative hotel-local clock and serialization guard, a human reason, a current active stay/occupant, a ready and enabled target room, no competing active stay, no conflicting confirmed booking and no active maintenance block. Expired-but-unreleased maintenance blocks still forbid transfer.

One plan includes both the **confirmed reservation's room ID** and the **active stay's room ID**, because the current Workpeg hotel schema requires them to match. The old room becomes dirty; the target room remains physically ready until the stay is checked out. Occupant links stay attached to the same stay and are not recreated. An audit **intent** records old/new room, actor, time and reason, but is *not committed*.

Service-request history retains its original physical room. Unresolved issues relating to the vacated room are explicitly surfaced by ID for staff review; they are **not automatically retargeted, resolved, duplicated or deleted**. For an active guest, the `request_view` projection now authorizes historical request status by the *same current stay and verified occupant*, not the historic room ID. New guest requests still require their current room, and older-room request reopening still requires separate staff handling.

After a confirmed transfer, existing checkout contracts will dirty the **newly occupied** room rather than the former room. Staff need to schedule housekeeping for both rooms independently.

## Current limitations and hosted gates

This PR adds **only pure, deterministic business-rule plans** and synthetic tests. It does not expose a write endpoint, deploy a Function, access real Workpeg tables, mutate a reservation, move a guest, or grant staff rights.

- `OperationContext` is not an authentication mechanism. A provider-supported adapter must derive actor, hotel and department from a signed-in authorized staff session, hold a genuine write guard and enforce durable unique operations.
- The canonical `stays` and `reservations` tables **cannot preserve prior room assignments by themselves**. Before a live writer is enabled, maintain a durable audit/movement ledger, including current/historical room mapping, actor/reason, timestamps, readback and retention rules.
- The room transfer requires multi-record consistency. Until Workpeg supports an authoritative serialization/reconciliation protocol, partial writes must result in a truthful pending/reconciliation state — never automatic retries or a success message.
- Service requests are maintained unchanged. Their full Workpeg/postgreSQL source-of-truth and visibility bridge is still unresolved under WOR-62. The `service_requests` parameter must be a complete, trusted same-hotel snapshot; the current offline function cannot prove a caller has supplied a complete ledger.
- Historic room-specific requests stay associated with their originating room; any open ticket tied to the old room needs staff review and cannot be silently moved to the new room. Expired or checked-out guest sessions never gain historical ticket access through the projection.
- The guest room-QR/stay-session mechanism must be revalidated against the **new** room after transfer; the old room's QR must not retain access.

## Verification

```bash
python -m unittest tests.test_room_transfer tests.test_checkout_housekeeping -v
python -m unittest discover -s tests -v
python -m compileall -q ui function domain tests
workpeg ui build ui/
python -m unittest tests.test_release_candidate -v
```

Tests cover old/new room state, guest historical ticket visibility and scope, new-request current-room enforcement, booking overlap, dirty/disabled/occupied/blocked destination, expired unreleased maintenance, wrong business/hotel/role, stale context, missing serialization, duplicate idempotency, incomplete readback and checkout after transfer.

**WOR-12 stays In Progress** until separate authenticated staff sessions, actual hosted Workpeg writes, guaranteed request history, safe concurrent operations, committed audit and consistent room board can be demonstrated.
