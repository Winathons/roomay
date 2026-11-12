# WOR-54 — offline checkout and housekeeping gates

This document describes domain command plans only. Checkout and room readiness
are **not enabled as Workpeg writes**. The plan objects have `persisted=False`;
passing their checks does not check a guest out, authorize a real staff member,
or save a room update.

## Checkout contract

`domain.checkout_commands.prepare_checkout` accepts only a currently
`checked_in` stay whose confirmed reservation and room still agree. It requires
a fresh complete hotel snapshot, same-business and trusted hotel-mapping
claims, an authorized owner/operator, manager, or receptionist claim, an
authoritative clock, an explicitly configured IANA hotel timezone, and a
claimed server-side serialization guard. A hotel-local operational date and
checkout timestamp must agree with that clock; naive, future, invalid-zone,
and cross-date timestamps fail closed. A guest who is overdue remains checked
in until this separate checkout plan is prepared.

The plan contains before/after versions of the stay, all registered occupants,
and room. It marks the stay checked out, gives `left_at` to occupants who have
not already departed, and marks the room `dirty`. It leaves reservations,
room enablement, maintenance blocks, and service-request history unchanged.
Already-departed occupants keep their original departure time, and checkout
may close the stay after all registered occupants have already departed.
Unregistered occupants, late departure history, occupants arriving after
checkout, duplicate checkout, and mismatched stay/reservation/room data are
refused.

Operation IDs are deterministic within business, hotel, stay, and
idempotency-key scope. The operation signature binds the intended timestamp,
occupants, room and housekeeping change. A matching prior operation requires
read-back; reusing its key for different inputs is rejected. These values do
not make a Workpeg row unique. A future writer needs a durable uniqueness
record/ledger or equivalent verified primitive before attempting any row
write. Uncertain outcomes are never retried blindly. The read-back classifier
requires matching operation evidence and all affected rows; missing evidence
or partial/conflicting rows require manual reconciliation.

## Housekeeping transitions

| Transition | Permitted offline actor claim | Gate |
| --- | --- | --- |
| Dirty → Cleaning | Housekeeping department staff | Fresh complete snapshot, same business/hotel mapping, trusted hotel-local time, serialization guard |
| Cleaning → Inspection | Housekeeping department staff | Same gates; inspection may not be skipped |
| Inspection → Cleaning | Housekeeping department staff | Re-clean after a failed inspection; a fresh operation key is required |
| Inspection → Ready | Owner/operator or manager | Same gates plus complete maintenance/safety evidence, no physical occupancy, no active applicable room block, and room enabled |

Same-state repeats and unlisted transitions fail. Receptionists, guests,
maintenance, and other departments cannot alter housekeeping state. A manager
or owner approval is required to pass Inspection to Ready; it cannot skip
Inspection.

Ready is refused if the room has an active checked-in stay, is disabled, has an
active maintenance block on the hotel-local operating date, or has an unresolved
maintenance-department service request associated with that room. Readiness
operations only change the room's housekeeping field; they never release a
maintenance block or change `rooms.enabled`. Because the current snapshot model
does not represent every possible physical safety hazard, absence of a block
or service request is not proof of safety; a future trusted operations policy
must provide a complete safety review signal before treating a room as ready.

Workpeg role/authentication claims in `OperationContext` are input assertions
to pure offline rules. Browser-provided booleans or roles are not trusted
authorization. A server-side Workpeg adapter must derive identity, business
membership, hotel mapping, department and authorization from authenticated
business state.

## Hosted write sequence still required

The pinned Workpeg SDK's currently verified Roomay integration does not provide
a demonstrated atomic multi-row checkout transaction or conditional compare
and swap. The following is a future contract, not an available implementation:

1. Authenticate the staff session server-side; verify role, department,
   business, trusted hotel mapping, and complete current reads for the stay,
   reservation, all occupants, room, maintenance blocks, relevant maintenance
   requests, and idempotency/audit record.
2. Acquire a real server-side serialization guard covering the stay, room, and
   any competing checkout/housekeeping operations. A client-supplied claim or
   stale fingerprint is not a lock.
3. Re-read under the guard, validate all before-state values and use a durable
   unique idempotency operation record. Reused key with changed signature must
   stop without writes.
4. Apply the stay, occupant, room, and audit/idempotency effects under a
   verified atomic transaction. If Workpeg cannot provide that, an explicitly
   reviewed journal/recovery protocol and human reconciliation are required;
   independent PATCH calls can leave a checked-out stay with active occupants,
   a room still Ready, or a room Dirty while still occupied.
5. Read back every affected row and the operation/audit record while the guard
   remains held. Report success only after exact agreement. A timeout, 401/403,
   missing row, stale fingerprint, partial update, or mismatched audit record
   must retain an uncertain/error state and prevent blind retry.
6. Release the guard only after verified completion or a recorded manual
   reconciliation state. Do not present a local plan as a committed checkout.

Workpeg Tables and Rows calls have not been used for this task. Hosted identity,
permissions, atomicity/guard support, audit storage, persistence, read-back,
timeouts and retry behavior remain unverified under WOR-28. Do not run live
checks, create tables, or enable UI write buttons as a substitute.

## Room transfer and audit dependency

Room transfer is not implemented in this phase. The current adapter correctly
rejects a service request whose recorded room differs from the stay's current
room. Do not rewrite historical request rows. A later WOR-12 phase needs an
authorized, serialized room-move record with source/destination room, effective
time, actor, reason, occupant handling, reservation update policy, and a stable
audit link so that old requests retain their original room context while new
requests use the current room.

## Verification boundary

The automated tests use fictional hotel fixtures and deterministic timezone
stubs. They validate command preparation, transition gates, idempotency
contracts, and read-back classifications in memory. Test-local application of
a plan validates a copied snapshot only; it is not hosted persistence, a real
checkout, a live cleaning operation, authorization enforcement, or proof that
Workpeg can safely serialize the required writes.
