# WOR-28 — restricted-account permission acceptance (read-only)

**Status (November 10, 2026):** Prepared procedure, **not a completed live staff test**. This is the remaining M0 engineering acceptance gate. Keep WOR-28 **In Progress** until an owner observes and records the results from independent authenticated Workpeg accounts.

## Verified starting point — do not redo

- The owner reports that the isolated **Roomay AI** development business has all nine canonical Workpeg tables across `roomay_hotel_v1` and `roomay_requests_v1`. They are owner-only (`700`).
- The owner also reports fictional **Room 205**, a registered guest, confirmed reservation, active stay, Housekeeping extra-towels request and an audit row persisted and displayed by the read-only receptionist app. The original `room_types` test row (capacity 3) was preserved.
- PR #31 supplies the authenticated, read-only receptionist view. PR #32 supplies offline staff-action and complete-audit validation contracts, **not** real Housekeeping login or writes.
- The latest owner-observed request audit still had a **pending** event. Do not acknowledge, resolve or otherwise modify that request until an independently authorized reconciliation verifies a complete committed chain.
- Earlier namespace, migration and first-row issues are historical. **Do not** recreate tables, change schemas, re-seed rows or add a new database for this test.

## What this test can and cannot establish

Workpeg [Tables & Rows](https://developers.workpeg.com/docs/latest/tables/) documents three permission digits: owner / all business staff / public, with bit flags read=4, write=2 and share=1. `700` therefore permits the owner but gives no ordinary business-staff or public access. Individual table and row grants are documented, but **no field-level masking or department-group grant** is documented. The existing service-request row contains private guest/stay information and free text; do **not** give staff direct read grants to it merely to demonstrate an inbox.

The immediate goal is to **observe real owner access and real non-owner denial**, not to enable a Housekeeping operation. The authenticated browser app uses Workpeg's real APIs; `--fake-cloud` is *not* a mock backend. This test cannot establish staff-action authorization, role mapping, secure server projection or concurrent-write safety.

## Strict preflight (owner-operated)

1. Confirm the Workpeg browser profile belongs to the isolated **Roomay AI** development business and `roomay` Peg. Do not use production or any real hotel account.
2. Obtain a **separate, legitimate non-owner test staff account** already authorized as a business member, if available. It must not own the tables or have individual table/row grants. If none exists, record **BLOCKED — separate account unavailable** and stop; do not create users, invite people or change permissions as part of this read-only test.
3. Use a separate browser profile or private session for the restricted account, to prevent the owner's authentication cookie from contaminating results. Verify the displayed signed-in account and business from Workpeg's own UI, **not** a typed form field or URL parameter.
4. Before each session, verify the target `/b/<business_id>/reception` route contains the **same privately verified Roomay AI business UUID**, not a guessed business or developer-portal identifier. Do not post the UUID publicly.
5. If using a local server, follow the already reviewed `docs/dev-smoke.md` safe `WORKPEG_BIND_HOST=127.0.0.1` and `--peg-namespace roomay` setup. Opening a previously compiled localhost page without a real authenticated session does **not** count as a live test.

**No changes authorized:** table or row writes, permission grants, staff invitations, token generation, backend Function publishing, Peg installation, fake credentials, direct untrusted HTTP requests, or browser-console scripts that impersonate Workpeg users. No Workpeg secrets, bearer tokens, cookies, guest names, row payloads, UUIDs or internal request IDs in evidence.

## Read-only acceptance matrix

| Session | Read-only action | Expected evidence | Result |
| --- | --- | --- | --- |
| Owner, Roomay AI | Open real `/reception` and click `Refresh records` | Existing fictional Room 205 workflow loads from authenticated Workpeg data; no fixture fallback | **NOT YET OBSERVED IN THIS TEST** |
| Separate non-owner business staff, **without grants** | Open same approved business reception route; allow only existing page GETs | Private owner-only tables/rows are **not disclosed**. The page must fail closed or display an access-safe empty/error state; raw request or guest details must not appear | **NOT YET OBSERVED** |
| Signed out (optional) | Open route in signed-out profile | Authentication gate or rejected read; no data | **NOT YET OBSERVED** |
| Nonmember of Roomay AI (optional, only if account exists) | Attempt normal authorized app navigation to this business; no URL enumeration | Business/session access denied, with no private rows | **NOT YET OBSERVED** |

**Important:** Workpeg list endpoints can omit tables a user cannot read. An empty list alone is **not** proof that direct access is denied. Record the exact sanitized UI outcome and, if the page actually issues them, HTTP status for read-only `GET` requests. `401`, `403`, `404`, or a filtered response can represent different failure modes; do not invent a specific expected status. Never copy response bodies. If the page has no existing read path that tests a direct table/row permission, record **NOT VERIFIED** rather than bypassing the app.

## Manual procedure

1. **Owner baseline:** In the owner profile, verify business and namespace, open the current approved receptionist route, select **Refresh records**, and record whether the fictional Room 205, request and audit display as expected. Do **not** click a developer write/seed action. If owner reads unexpectedly fail, stop before interpreting non-owner results.
2. **Restricted session:** Close or separate the owner profile. Sign in as the independently verified non-owner staff member in a separate profile. Navigate through the normal Workpeg UI to the same dev business and approved reception page. Use only the existing read/refresh controls; do not change table or user permissions.
3. **Review network evidence carefully:** If helpful, filter DevTools Network to read-only `GET` requests for the Workpeg Tables API. Record method, sanitized endpoint category (tables list / table metadata / rows), status and whether the application revealed private guest/request content. Do not capture URLs with actual business/table/row IDs, request headers (`Cookie`, `Authorization`), bodies, or staff identifiers. A blank list/error is a limited observation, not proof of backend department scoping.
4. **Compare, do not mutate:** Confirm the restricted profile cannot view owner-protected guest/request information and did not obtain owner permissions. Return to the owner profile, refresh again, and confirm the same fictional records remain unchanged.
5. **If blocked:** Record the reason (no separate staff account, no business membership, route unavailable, unable to isolate sessions, unclear permission outcome, unexpected disclosure). Do **not** remediate by changing `700`, granting a table/row, creating a new schema, or connecting `WORKPEG_PK`.
6. **Owner evidence:** Attach only redacted screenshots or a short text report to [WOR-28](https://linear.app/workpeg/issue/WOR-28) and mark each observation **PASS / FAIL / BLOCKED / NOT VERIFIED**. This procedure's existence is **not** acceptance evidence.

### Evidence report template

| Field | Owner | Restricted account |
| --- | --- | --- |
| Test date and SDK (`0.152.0` expected) | — | — |
| Confirmed correct Roomay AI dev business (yes/no) | — | — |
| Workpeg account type/role, **without personal identifiers** | Owner | Non-owner member / blocked |
| Existing receptionist route GET attempted? | — | — |
| Sanitized outcome/status and UI state | — | — |
| Any protected guest or request information disclosed? | — | — |
| Separate session verified? | N/A | — |
| Result (PASS / FAIL / BLOCKED / NOT VERIFIED) | — | — |

### Stop and escalation criteria

- **Any non-owner disclosure** of owner-only request/guest rows is a security defect: stop, save redacted evidence, keep release disabled and investigate. Do not attempt a staff write.
- **Any uncertain identity or business binding** invalidates the test.
- **A denied read does not authorize a grant or prove that a staff action will work.** The next phase must verify trusted server-side identity/department mapping and a privacy-safe staff projection before any positive Housekeeping access.
- Do not mark WOR-14, WOR-22, WOR-28 or WOR-34 Done on documentation alone. Once a genuine second-account denial is evidenced, review whether WOR-28's exact remaining criteria are met. Other product requirements remain independently gated.

## Later: real Housekeeping workflow (separate reviewed work)

The merged `domain/staff_actions.py` already prepares an offline request action, but its trusted identity resolver, business-scoped reader and serialized writer are *not* implemented. Workpeg's documented table/row grants are not private-field masking. Before a live Housekeeping acknowledgement, select and review a supported **server-side trusted authorization gateway** (or an explicitly approved privacy-safe schema redesign), ensure complete **committed** audit history, and independently prove that the gateway returns only Housekeeping-scoped fields while all direct owner-only rows remain inaccessible. This is a future integration, not part of this M0 read-only permission check.

References: [Workpeg Tables & Rows](https://developers.workpeg.com/docs/latest/tables/), [Getting Started](https://developers.workpeg.com/docs/latest/getting-started/), `docs/wor-49-authorized-staff-requests.md`, `docs/reception-live-integration-and-qa.md`.
