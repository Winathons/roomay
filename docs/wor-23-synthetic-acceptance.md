# WOR-23 — Synthetic acceptance walkthrough and live verification gate

**Last reviewed:** 2026-11-12  
**Status:** Offline acceptance automation only. **Not a live Workpeg end-to-end demonstration.**

## Purpose and source of truth

The real ROOMAY demo must show: authorized reception booking, verified physical
check-in, a stay-scoped guest AC request, one **persisted** ticket and committed
audit event, a department worker seeing and updating the **same** request,
an authorized maintenance block preventing unsafe allocation, a safe alternative
room, and checkout/housekeeping handoff visible after a separate reload.

That requirement is tracked by [WOR-23](https://linear.app/workpeg/issue/WOR-23).
None of the current purely offline tests proves that joined flow. They create
plans and use deep-copied Python records for the next step; no Workpeg table
writes, backend OIDC callback, guest notifications or phone/Vapi actions occur.

## Run the safe offline rehearsal

From the cloned repository root, using the pinned Workpeg environment:

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p test_wor23_acceptance.py -v
python -m unittest discover -s tests -v
python -m compileall -q ui function domain tests
workpeg ui build ui/
```

All commands must be run **without** `--fake-cloud`, customer data, backend
tokens, or external guest/PMS/AI providers. The GitHub Actions `Roomay UI Check`
runs the same offline Python test discovery and Workpeg compiler; no live
Workpeg connectivity should be required.

The focused test uses an 8-room / 2-room-type subset of existing deterministic
fixtures, plus fictional existing bookings, an active registered stay, a dirty
room and a maintenance block. It checks the following end-to-end
**in-memory proposals**, always `persisted=False`:

| Step | Offline expected evidence | Real Workpeg acceptance |
|---|---|---|
| Walk-in request | Pending reservation, no room or stay | Authorized business-scoped row saved and reloaded |
| Staff confirms room | Room 204 proposed; not booked by test | Atomic/serialized confirmed assignment, verified saved reservation |
| Staff checks in guest | Proposal adds one stay and registered occupant | Durable authorized check-in, 2+ linked rows verified |
| Guest asks for AC | Maintenance ticket plus **pending** audit plan | Verified active-stay session, exactly one committed ticket/audit |
| Desk routes task | Assigned to maintenance, no automatic notification claim | Staff inbox reads the exact same request from authoritative writer |
| Maintenance acknowledges | Status event records actor; deliberately late vs acknowledgement target | Durable actor/time, idempotency and overdue status after reload |
| Maintenance resolves | Proposed event chain and guest projection show resolved | Independent guest session reads same committed resolved status |
| Room block | Candidate room 206 rejected; alternative 202 planned | Authorized block saved, no unsafe booking race, alternate verified |
| Checkout | Plan changes stay, occupant departure and room to dirty | Authoritative multi-row readback/reconciliation; room still needs cleaning |
| QR/wrong business | Unverified QR alone cannot read guest profile | Hosted wrong guest/business/staff role receives denial |

**Known scope exclusions:** phone/PMS/payment processing and WhatsApp are not
connected acceptance paths. Remi's voice demonstration does not prove request
persistence, staff notification or a real human transfer. Failed AI,
notification, network or backend calls must show a truthful unavailable/unknown
state or manual reception fallback, not a fictional successful save. Do not
present synthetic screenshots as hosted service evidence.

## Live demonstration — owner-led checklist (NOT executed by these tests)

Use only the authorized **Roomay AI** development Workpeg business, genuine
vendor-supported authenticated sessions, fictional records, and an owner-approved
test window. Do not create new schemas/records, invite staff, expand `700`
table permissions, publish Functions or expose guest links merely to run
this checklist.

1. Record the exact approved Peg, installed business, project release/version,
   test dataset and operator roles privately. Check verified 8+ rooms and
   both room types. Avoid leaking tokens/business identifiers to screenshots.
2. With **receptionist** session, create a fictional walk-in request. Record
   server-confirmed pending status. Re-open in an independent session and
   observe the same record ID. Do **not** confuse pending with checked-in.
3. With a trusted authority/concurrency guard, confirm a safe room and physically
   check in a registered occupant. Verify linked reservation, stay and occupant
   records across a new authenticated session. If unsupported, mark **BLOCKED**.
4. With a verified guest session for the active stay, explicitly confirm one
   AC request. Verify precisely one committed request **and** audit entry in
   the designated authoritative store; refresh and read both by the canonical
   IDs. A voice model or webhook invocation is not itself persistence.
5. With a scoped **maintenance** account, observe the *same* request in the
   authorized queue, acknowledge and resolve. Refresh independently as guest:
   same request ID, same final status. Verify an unrelated department, guest,
   nonmember and business cannot access it. For deliberately late acknowledgement,
   record target vs actual time rather than masking SLA violation.
6. With the permitted staff authority, create a maintenance block on another
   fictional room; try confirming overlapping reservation to that blocked room.
   It must fail. Record the next safe alternative and verify its saved assignment
   without double allocation under simultaneous attempts.
7. Check the active stay out with independent authorized staff confirmation.
   Reload: reservation history retained, physical stay ended, registered
   occupants left, room is **dirty** rather than automatically ready. Verify
   the separate housekeeping actor transitions with actor/time/audit.
8. Exercise failure paths: wrong business, wrong role, wrong guest, reused
   idempotency key, conflicting booking, timed-out request/audit write, service
   outage, stale state, ambiguous retry and altered room identity. Record
   sanitized 401/403/error messages and reconciliation, never sensitive
   request text or raw tokens.
9. Reopen in a separate authorized session to prove persistence and attach
   redacted screenshots or a short screencast. Label each screen/step
   **VERIFIED LIVE**, **OFFLINE ONLY**, **NOT IMPLEMENTED** or **BLOCKED**.
   A video replay is not live persistence proof.

## Release evidence matrix — present state

| Capability | Status | Dependency |
|---|---|---|
| Pure room eligibility, booking, stay and request planners | **OFFLINE ONLY** | Existing unit suites, WOR-50 and this test |
| Explicit bad-role and wrong-guest denial rules | **OFFLINE ONLY** | WOR-22; hosted Workpeg permissions still unverified |
| Authenticated browser read-only receptionist | **OWNER-REPORTED DEVELOPMENT READ**; role acceptance pending | WOR-28/29/34/52 |
| Standalone backend access to Workpeg Tables | **BLOCKED**: developer PK is not a server Tables credential | WOR-61, Workpeg vendor |
| OIDC staff callback in standalone backend | **UNVERIFIED** | WOR-61, actual registered client/hostname |
| Single guest request/audit writer visible on both surfaces | **BLOCKED**: PR #37 PostgreSQL vs Workpeg tables not synchronized | WOR-62, WOR-65 |
| Physical booking/check-in/checkout and housekeeping writes | **UNVERIFIED HOSTED** | WOR-11/12/14, concurrent-safe authority |
| Voice/AI/notifications to committed staff service request | **NOT INTEGRATED** | WOR-63/65; Remi prototype != committed ticket |
| Fresh independent session, cross-role isolation, audit/readback | **BLOCKED** | WOR-23 final live acceptance |
| Publishing to production | **NOT AUTHORIZED** | WOR-25, WOR-33, owner approval |

This matrix must be updated from actual sanitized run evidence, not inferred
from a green CI check. The post-hackathon product must retain the same safety
standards.

## Handoff

- Baseline cross-workflow tests: `tests/test_hotel_workflow.py`.
- Integrated eight-room planning regression: `tests/test_wor23_acceptance.py`.
- Release artifact safety checks: WOR-33.
- Data integrity/actor-time audit contracts: WOR-22, WOR-49, WOR-54.
- Roomay blueprint and Linear are the sources for full product acceptance.

**WOR-23 stays In Progress** until real authenticated Workpeg records are
created/read under the approved integration, cross-role authorization and
the full guest→staff→guest ticket/status trace are demonstrated and reviewed.
