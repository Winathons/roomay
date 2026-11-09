# Workpeg integration readiness — WOR-6

This is a **development runbook**, not evidence that a live Workpeg connection is already working.

## Current confirmed state (2026-11-06)

- GitHub: `Winathons/roomay`, default branch `main`.
- Local developer verified Python 3.13.5 and Workpeg SDK `0.152.0`; UI build and offline doctor pass in the pinned environment.
- Starter page displayed `Hello from roomay` at `localhost:8081`.
- **Approved:** Developer portal shows the `roomay` Peg registered and **Approved**; the owner confirms it is associated with the separate `Roomay AI` development business.
- **Workpeg support-confirmed:** a Peg UI using authenticated staff-session table helpers can test data **locally with `--fake-cloud` and `--peg-namespace roomay` without a published/installed release**. Function/save-hook publishing is a separate workflow.
- **Owner-reported (updated 2026-11-09):** the first `roomay_hotel_v1/room_types` table is present with owner-only permission `700`; fictional row create, update, read-back and persistence after independent browser reload were verified. This supersedes the earlier missing/unreadable report. The remaining eight tables and staff/row-level permission behavior remain unverified.
- **Not yet verified:** table creation, row create/update, persisted read-back after reload, or multi-user permissions. No release is published and this task does not perform hosted writes.

## 1. Separate development business (owner action)

WOR-28 provides an offline-verified diagnostic source module, but WOR-34 no
longer registers `/b/<business_id>/dev-smoke` in the release router. See the
[owner runbook](dev-smoke.md) for SDK evidence,
fake-cloud run instructions, exact manual test steps and an offline screenshot. No live
persistence/permissions evidence has been added; WOR-28 and WOR-6 remain In Progress.

Use a **dedicated Workpeg development account/business** containing fictional hotel data. Do not develop against a customer hotel or an intended production account.

1. Sign in to the official Workpeg platform/developer console.
2. Create or select a development business with no production hotel records.
3. Confirm the account is an authorized staff member of that business.
4. Establish whether `roomay` is an available Peg namespace in that business, and check the developer/publishing workflow with the organizers.
5. Give teammates only the minimum needed access. Store tokens outside Git and do not share secrets in issue comments/screenshots.
6. Record only non-sensitive confirmation: business nickname (e.g., `Roomay Demo Hotel`), access status, screenshots without customer data, any blockers.

**Important:** `workpeg ui serve ui/` on localhost only tests the UI. Workpeg's `workpeg.*` table helpers operate in an authenticated Workpeg business context. The SDK says they resolve the active business from `/b/<business_id>/...` and send the Peg namespace plus authenticated session.

The `--fake-cloud` development flag **is not a sandbox**. It changes local hosting/origin, can expose the server on the LAN, and sends operations to the real Workpeg API under the signed-in account. Workpeg support has confirmed this is the supported local **Peg UI table test** path without a release; it should be run **only by the owner after verifying the Roomay AI business**, with `WORKPEG_BIND_HOST=127.0.0.1` to prevent LAN exposure. See [dev-smoke.md](dev-smoke.md).

References:
- https://developers.workpeg.com/docs/latest/getting-started/
- https://developers.workpeg.com/docs/latest/projects/
- https://developers.workpeg.com/docs/latest/tables/

## 2. Backend-first? No: use native platform facilities

The primary staff application should use the Workpeg Python UI and its authenticated table helpers, without building an unnecessary second API/database.

Confirmed SDK helpers (call with `await` within supported async UI code):

| Purpose | Helper |
| --- | --- |
| List/create schema | `workpeg.get_tables(namespace)`, `workpeg.create_table(schema)` |
| Read schema | `workpeg.get_table(table_uuid)` |
| Paginated rows | `workpeg.get_rows(table_uuid, limit=100, offset=0)` |
| Read one row | `workpeg.get_row(table_uuid, row_id)` |
| Insert | `workpeg.add_row(table_uuid, row)` |
| Edit | `workpeg.update_row(table_uuid, row_id, patch)` |

These target the currently authenticated business; the Peg namespace is applied automatically. Each Workpeg table has typed columns and business/individual permissions.

Two key design constraints:

1. **Never assume public guest access works like authenticated staff access.** The SDK documents staff membership requirements for its REST table APIs. Confirm a supported public channel before implementing a guest portal, or design a tightly scoped server-only gateway. Never embed developer tokens in the browser.
2. `PATCH` replaces the row's **entire** `data` object when that field is supplied, despite being a partial update of the row overall. Read, merge relevant `data` keys, then save; do not wipe other fields accidentally.

## 3. First persistent-data smoke test (fictional only)

After authenticated dev business access is available:

1. Create a small `Roomay Dev Smoke` table belonging to the Roomay Peg and a development-only namespace, e.g., `roomay_smoke`.
2. Define required `room_number` text and optional `status` text columns using supported table schema types. Keep table access owner-only unless a second staff account is specifically being tested.
3. Insert **one fictional row**: room `201`, status `ready`, via documented Workpeg `create_table` and `add_row` helpers or the platform's authorized UI.
4. Retrieve it using `get_tables` and `get_rows` under the **correct** business and namespace. Refresh and confirm persistence.
5. Update its status to `dirty` while preserving other `data` keys, refresh and re-read.
6. Test that a different/unauthorized account cannot read or modify the test records. If a second staff test account is unavailable, record that limitation.
7. Capture redacted test evidence, including table/row lookup and any error details, without session cookies/tokens.

**Acceptance gate:** proven persistent read/write with authorized session, repeatable from a fresh login; no data outside isolated development business changed.

Do **not** connect actual guest identity records, reservations, customer payments, or hotel PBX integrations during this smoke test.

## 4. Report evidence back in Linear

Comment on [WOR-6](https://linear.app/workpeg/issue/WOR-6/configure-isolated-workpeg-dev-business-sdk-identity-and-access) with:

- Development business created/selected? (yes/no)
- Authorized session and Peg namespace tested? (yes/no)
- First table created and row persisted after refresh? (yes/no)
- Second-account negative permission test? (pass / not yet possible)
- Unexpected errors, supported SDK version, and exact command path
- Screenshot with sensitive values removed
- Open blocker for public guest access / publishing, if any

Keep WOR-6 **In Progress** until the table test actually succeeds.

## 5. Later Roomay architecture (not part of smoke test)

The offline hotel model and fictional fixtures already exist in `domain/` (WOR-8 Phase A; 25 tests). Once [WOR-28](https://linear.app/workpeg/issue/WOR-28) proves real Workpeg table persistence and permissions, [WOR-29](https://linear.app/workpeg/issue/WOR-29) connects approved schemas to those tables and safely seeds fictional room records. Do not provision all tables or real guest data before validating Workpeg behavior.

The product goal remains a Workpeg-native hotel operating experience with precise reservations vs. in-house occupancy and separate maintenance/housekeeping readiness, using synthetic data until privacy and correctness are verified.
