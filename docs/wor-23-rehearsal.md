# WOR-23 — ROOMAY demo rehearsal and evidence matrix

**Status: synthetic rehearsal prepared; real Workpeg end-to-end acceptance blocked.** Last updated 12 November 2026.

## What this validates

The **existing** local guest/staff sample journey in `tools/guest_chat_demo.py` uses synthetic records and in-memory state. It does not use Workpeg tables, staff OIDC, the separate PostgreSQL guest backend, telephony, AI models, or payments. The QA role switcher is not real authentication.

This rehearsal deliberately exercises the **already-implemented** browser journey rather than duplicating its UI. It also separately checks the **pure offline** room-safety/reassignment planner. These are two distinct synthetic snapshots — not one real committed cross-platform transaction.

### One-command machine-readable rehearsal

From repository root with Python dependencies installed:

```bash
python -m tools.wor23_rehearsal
python -m unittest tests.test_wor23_rehearsal tests.test_guest_chat_demo -v
python -m unittest discover -s tests -v
python -m unittest tests.test_release_candidate -v
```

The command exits nonzero on an assertion failure and prints **sanitized JSON** only when the synthetic workflow passes. The report is labeled `synthetic_rehearsal_passed`, `evidence_scope=local_process_only`, and `record_writes=none_external; process_memory_only`. It also lists functionality that is **not verified**. The output has no session cookies, guest identifiers, raw guest names or secret credentials.

The existing fictional inventory factory creates **ten rooms (201–210), not eight** as the original WOR-23 outline requested. It includes standard and suite room types, a future reservation, a walk-in reservation, a checked-in stay, a dirty room and a maintenance block. Changing it simply to match the old issue count would break valid existing regression assumptions.

### Human browser walkthrough — local QA only

Start the sample server:

```bash
python -m tools.guest_chat_demo --port 8765 --enable-local-qa
```

Open **http://127.0.0.1:8765/__qa/** on the same computer (do not publish or tunnel this local role-picker). The sample app uses a **single local role in one session cookie**; choose the correct workspace on `/__qa/` before following each route:

1. **Guest / My Stay**: choose **Open My Stay**. The fictional guest is staying in Room 205. Type `Please bring extra towels to room 205.`, review the suggestion and press confirm. The new request should display `Received`. UI text explicitly states it has **not been sent to hotel staff**.
2. **Reception**: return to `/__qa/`, select Reception. The same synthetic ticket should appear in the service requests queue. Assign it to Housekeeping; its status becomes `Assigned`.
3. **Housekeeping**: return to `/__qa/`, select Housekeeping. On the assigned ticket, take **Acknowledge → Start → Resolve** in order. The ticket should pass through `Acknowledged`, `In Progress`, and `Resolved`.
4. **Guest readback**: return to `/__qa/` and explicitly select **Open My Stay**. Reload the page; the original guest should see **Resolved** on their request.
5. **Negative-case demonstration**: opening `/stay` directly while the *same demo cookie* is in Housekeeping role should return **403**, not leak guest data or silently switch roles. Recover via `/__qa/`, select Guest, then verify status again. A new independent QA session does **not** inherit the first session's tickets.
6. Show the synthetic banner. Do not suggest a real hotel received a request; do not expose the role-switcher to external users.

If browsers are unavailable, run the automated command instead and capture the local console output or prepare a **clearly labeled synthetic screencast**. Neither is equivalent to hosted acceptance.

## Acceptance / regression matrix

| Expected behavior | Evidence available | Live acceptance |
| --- | --- | --- |
| Fictional guest stay, room inventory and reservation/maintenance baseline | Existing synthetic fixtures, regression tests | **No real Workpeg test-business proof from this PR** |
| Guest explicitly confirms extra towels | Deterministic command, HTTP tests, local QA flow | Blocked: Workpeg-authorized guest channel |
| Reception assigns; Housekeeping acknowledges, starts, resolves | Local in-memory state, canonical request event/audit simulation, role-specific projections | Blocked: actual authorized Workpeg staff actions and durable audit |
| Guest sees resolved after switching back and reloading in same server process | Rehearsal and existing HTTP test | **No persistence across process restart** |
| Wrong-room / wrong role / another guest session | Rehearsal plus existing negative security tests | Real Workpeg multi-role negative testing pending |
| Duplicate confirmation / failed upstream provider | Rehearsal and request-contract tests | Real concurrency, notification retry and outages pending |
| Maintenance block prevents reassignment to unsafe room | Separate fixture with `prepare_safe_reassignment` unpersisted plan | Authorized room-block write + independent room-board readback pending |
| Walk-in check-in, checkout, cleaning, and confirmed booking rules | Separate `test_reservation_commands`, `test_front_desk_checkin`, `test_checkout_housekeeping`, `test_maintenance_commands` suites | **Not yet a connected browser or hosted workflow** |
| Room move and historical ticket privacy | Separate `test_room_transfer` and service-request tests | Cross-system atomic movement + hosted historical request readback pending |
| Phone/PBX, Vapi, LLM, PMS and payment | Not part of the local rehearsal | Not verified; do not demonstrate as live |

## Demo readiness blockers

1. **WOR-61:** Workpeg has not yet supplied an approved authenticated external Function/data invocation contract or registered real OIDC callback.
2. **WOR-62:** PR #37's PostgreSQL request/audit store differs from the current Workpeg receptionist's operational request/audit tables. No single approved writer and staff read projection have been proven.
3. **WOR-65 / WOR-14 / WOR-22:** Real guest request → Workpeg department queue → department transition → guest readback, with permissions, audit and reconciliation, remains unverified.
4. **Workpeg test business:** Separate authenticated owner, receptionist and department staff testing is outstanding; the read-only Reception Peg does not authorize the local QA role picker or live writes.
5. The local sample process loses state on restart. A page reload inside the same server process is **not durable persistence**.

### Evidence collection after the bridge is approved

In the owner-authorized fictional **Roomay AI** Workpeg business, capture the exact Peg/build version, UTC timestamps, sanitized before/after request status, independent staff session scopes, read-after-reload results, audit event linkage, duplicate-operation denial and denied wrong-business tests. Screenshots must omit cookies, keys, guest personal data and bearer URLs. Never broaden current owner-only `700` table rights merely to make a demo pass; obtain approved least-privilege permissions first.

**Do not mark WOR-23 Done** merely because this offline code and CI pass. The issue's actual cross-screen **Workpeg-persisted** acceptance requires approved external integration, separate-session hosted evidence and reviewed demo steps.
