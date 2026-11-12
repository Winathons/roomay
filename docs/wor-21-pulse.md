# WOR-21 — Roomay Pulse, offline advisory analysis

**Scope:** deterministic, read-only manager suggestions from complete, validated Roomay hotel and service-request snapshots. This phase **does not** persist incidents, send notifications, change ticket statuses, block rooms, call AI, deploy a Function, or imply that a hotel manager has acknowledged an incident.

`domain/pulse.py` exposes:

- `build_pulse_snapshot(hotel, requests, context, as_of, policy)` — validates a single-business/single-hotel, complete and fresh hotel/request snapshot, with an explicitly authorized management context. It rejects malformed, duplicated, cross-hotel, unknown-room/stay and future-dated request records, rather than silently excluding untrusted source rows.
- **Incident suggestions:** group open, nonsensitive, canonically categorized requests by `category` within a deterministic fixed time window anchored to the first request (default 180 minutes; threshold 3). Use stable request IDs and room IDs, include timestamps and how many requests show an acknowledged timestamp. Multi-room patterns and repeated complaints from a single room are distinguished. Unrelated categories, resolved/cancelled tickets, and sensitive incidents are not included. The explanation **does not diagnose cause or assert a confirmed incident**. Each original ticket remains individually actionable and auditable in its existing lifecycle.
- **Overdue indications:** compare explicit authoritative observation time to each open request's existing `acknowledge_by` and `due_at`; the policy can add separate acknowledgement/resolution grace intervals. For reopened tickets the original acknowledgement deadline is not incorrectly reused as a fresh unacknowledged SLA. The result is an **advisory management alert** with `escalation_sent=False`; it does not perform a `transition_request`, schedule a job, or send staff notifications.
- `prepare_pulse_review(pulse, suggestion_id, action, notes, context, idempotency_key)` — prepares an unpersisted `accept` or `dismiss` audit intent for an explicitly verified manager, owner, or trusted incident manager. It requires a note, binds request IDs and an operation fingerprint, and refuses duplicate uncertain operations until readback. It does **not** accept the suggestion or write a decision in Workpeg.

## Privacy, provenance and authorization

The projection contains only hotel/request/room IDs, category, department, status, deadlines and request timestamps; **not** guest IDs, guest names, phone numbers, contact details, descriptions or sensitive ticket content. `sensitive=True` requests are excluded even from aggregates so their existence is not leaked. The manager view uses allowlisted fields only; never pass raw request rows or arbitrary AI-generated causal labels through the UI.

`PulseContext` and `PulsePolicy` are contracts, not authentication. A browser or AI can forge a dataclass, so **only a future trusted Workpeg adapter** may derive actor and business/hotel scope from real authenticated sessions and prove all pages of the request/room snapshot are complete. The authoritative `as_of` clock must also come from the trusted backend/hotel context. If the adapter cannot establish those facts, Pulse must fail closed.

Accepted/dismissed manager decisions require a future durable, access-controlled incident/audit ledger with approved retention and redaction (and a supervisor role mapping). **No such table or write adapter is claimed here.** Idempotency IDs and fingerprints don't establish durable uniqueness or atomic writes by themselves. As source requests change, cluster membership and deterministic suggestion IDs may change; a future persistence adapter must reconcile earlier decisions against current members before committing.

The canonical request categories are `air_conditioning`, `plumbing`, `extra_towels`, `room_service` and other values in `domain/service_requests.py`. The grouping is **not a causal diagnosis**; it makes no claims about floor-level defects, staff assignment, service request delivery or whether a room is safe to occupy. Do not automatically block a floor or trigger a guest-facing escalation.

## Why this phase is not live

WOR-21's owner notes mark Pulse a **post-MVP P2 optional feature** to integrate after real Workpeg-persisted requests, staff roles and audit correctness. This phase delivers only the independent analysis/review rules so it does not delay the primary guest request → department action → guest resolution workflow. The current Workpeg request authorization/write bridge and single source of truth remain pending WOR-61/62; manager UI and hosted acceptance are separately required.

## Reproducible offline verification

```bash
python -m unittest tests.test_pulse -v
python -m unittest discover -s tests -v
python -m compileall -q ui function domain tests
workpeg ui build ui/
python -m unittest tests.test_release_candidate -v
```

Synthetic tests cover three cooling reports vs separate food/towel complaints, deterministic order and bounded time windows, private and resolved requests, acknowledgement and resolution overdue boundaries, role/business/hotel rejection, partial/duplicate/future rows, no automatic escalation, and accept/dismiss audit intents.

**Keep WOR-21 In Progress** after the offline PR merges. It is not Done until an owner-approved Workpeg manager view consumes genuinely persisted staff-authorized request data and records reviewed decisions/audits.
