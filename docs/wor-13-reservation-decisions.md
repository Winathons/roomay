# WOR-13 — staff reservation decisions (offline safety contract)

**Implementation scope:** `domain/reservation_desk_commands.py` prepares staff-confirmation and cancellation **intents** against a complete, single-business hotel snapshot. No Workpeg tables are written, no room is reserved or released, no booking is confirmed, no audit is committed, and no revenue/payment is reported by this module.

The existing `domain/reservation_commands.py` remains the canonical reservation state engine:
- A `pending_confirmation` reservation **does not hold inventory** and never creates a stay.
- A `confirmed` reservation has an assigned room; physical occupancy starts only through the separate WOR-11 checked-in stay + occupant workflow.
- A `cancelled` reservation with no stay frees the *planned* allocation when actually committed to the authoritative store. A reservation already used by any stay cannot be cancelled through the reservation desk; it must go through the appropriate room transfer/checkout flow.
- The canonical `source` values are **`advance`** and **`walk_in`**. There is no separate stored `web` source today. `advance` must not automatically be called a verified online booking/payment.
- Room eligibility blocks occupied/disabled/maintenance-conflicted or overlapping assigned rooms. Future confirmation does not independently guarantee *arrival-day* housekeeping readiness: readiness must be checked again at actual check-in.

## Staff-reviewed operations

`prepare_staff_confirmation` requires a trusted same-business `WriteContext`, a genuinely held serialization guard, fresh full hotel snapshot, a confirmed staff review of inventory and booking terms, and an eligible room. The reviewer must match the authorized actor; review age must be at most 30 minutes and not future-dated. The booking must not already be past the departure date **in the configured hotel IANA time zone**. It proposes pending → confirmed, recording a separate audit intent with actor, timestamp, room and verified review flags.

`prepare_staff_cancellation` also requires a trusted context, serialized snapshot and one of the non-PII standardized reasons: `guest_requested`, `booking_error`, `hotel_unavailable`, `duplicate_request`, or `other_reviewed`. It refuses cancellation of a reservation associated with a stay, including a checked-out stay. It proposes pending/confirmed → cancelled with a separate audit intent and no automatic payment/refund operation.

Both return `ReservationDecisionPlan(persisted=False)`. Deterministic business-scoped operation IDs and signatures detect same-key different-operation conflicts **only when backed by an authoritative durable operation ledger**, which is not implemented here. Already-attempted keys require readback, not blind resubmission.

`reconcile_reservation_decision` classifies a full authoritative snapshot only when independently sourced operation evidence matches **and its audit is marked committed**. The result `reservation_decision_observed_do_not_repeat` is a *readback classification* and is not a substitute for proof that Workpeg authorized a real write. A still-pending source row, conflicting target or missing/corrupt evidence requires human reconciliation.

## Explicit vendor and integration dependencies

- Only a trusted backend/Workpeg platform boundary may derive actor membership, business scope, timestamps, review outcome, fresh complete table snapshot, and hold true per-room/date serialization through authorization, write, and readback. **Never accept `WriteContext` or review booleans directly from browsers, AI or voice inputs.**
- The currently documented Workpeg APIs do not establish a secure external writer, durable idempotency uniqueness, cross-table transaction, compare-and-swap or lock for Roomay's confirmation path. Until those are proven, **do not enable the confirmation/cancellation buttons** against hosted data or show successful booking states.
- Existing canonical `reservations` rows do not store staff confirmation time, cancellation reason or actor identity. Those are **audit intents only** in this PR. The owner must approve a separate authoritative audit schema/ledger and access/privacy rules before real updates.
- Never treat an online request, unverified contact, invoice, payment screenshot, prepaid QR or AI recommendation as a confirmed reservation/payment. Rate and guest contact are not part of the canonical hotel reservation schema; the read-only UI work under WOR-48 and Figma WOR-39 are separate.
- The current `Workpeg` vs PostgreSQL guest request authority decision (WOR-62) and supported external bridge (WOR-61) remain open. Real hosted acceptance requires fresh two-session concurrency tests, separate role denial, cross-business verification, persisted confirmation/cancellation and arrivals refresh, audit readback, and timeout recovery.

## Regression verification

```bash
python -m unittest tests.test_reservation_desk_commands tests.test_reservation_commands -v
python -m unittest discover -s tests -v
python -m compileall -q ui function domain tests
workpeg ui build ui/
python -m unittest tests.test_release_candidate -v
```

Tests use synthetic fixtures, no hosted Workpeg records, no real staff identities, no customer PII, no payment and no genuine writes. **WOR-13 remains In Progress** after this offline phase until production acceptance criteria are observed in an authorized Workpeg test business.
