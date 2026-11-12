# Workpeg integration readiness — WOR-6

This development runbook contains earlier setup procedures. For the current owner-verified live-data checkpoint and the **next required read-only restricted-account test**, see [WOR-28 restricted-account acceptance](wor-28-restricted-account-acceptance.md). Do not repeat earlier table or row creation steps.

## Current checkpoint (November 10, 2026; historical setup context follows)

- GitHub: `Winathons/roomay`, default branch `main`.
- Local developer verified Python 3.13.5 and Workpeg SDK `0.152.0`; UI build and offline doctor pass in the pinned environment.
- Starter page displayed `Hello from roomay` at `localhost:8081`.
- **Approved:** Developer portal shows the `roomay` Peg registered and **Approved**; the owner confirms it is associated with the separate `Roomay AI` development business.
- **Workpeg support-confirmed:** a Peg UI using authenticated staff-session table helpers can test data **locally with `--fake-cloud` and `--peg-namespace roomay` without a published/installed release**. Function/save-hook publishing is a separate workflow.
- **Owner-reported (updated 2026-11-10):** all nine canonical Workpeg tables now exist in Roomay AI with owner-only permission `700`. The `room_types` fictional test row (capacity 3) survived create/update/reload. The fictional Room 205 guest, reservation, active stay, registered occupant, extra-towels request and audit row were persisted and displayed by the read-only receptionist UI. These are owner observations, not independent staff-role evidence.
- **Still open under WOR-28:** independent restricted/non-owner staff denial and any allowed-role permission evidence. The request's latest audit event was owner-observed as pending, so staff transitions remain blocked pending authorized reconciliation. This documentation update performs no hosted calls, writes, grants or release.

## 1. Separate development business (owner action)

WOR-28 provides an offline-verified diagnostic source module, but WOR-34 no
longer registers `/b/<business_id>/dev-smoke` in the release router. See the
[owner runbook](dev-smoke.md) for SDK evidence,
fake-cloud run instructions, exact manual test steps and an offline screenshot. Owner-observed live
persistence evidence is now recorded for the fictional Room 205 workflow. WOR-6 is Done; WOR-28 remains In Progress until independent restricted-account permission acceptance.

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

## 3. Historical first persistent-data smoke procedure — do not repeat

The originally prescribed setup steps below are retained as project history. The first row persistence and later fictional Room 205 workflow were already verified by the owner; **do not create another table or seed again**. The next live test is **read-only** per [WOR-28 restricted-account acceptance](wor-28-restricted-account-acceptance.md).

Earlier setup instructions were:

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

WOR-6 is **Done** on the owner-verified persistence evidence. Keep WOR-28 **In Progress** until an independent non-owner permission test is observed, recorded, and accepted.

## 5. Later Roomay architecture (not part of smoke test)

The offline hotel model and fictional fixtures already exist in `domain/` (WOR-8 Phase A; 25 tests). The nine canonical schemas and fictional Room 205 workflow are owner-reported as persisted and visible to the read-only receptionist; WOR-29 remains In Progress pending its broader acceptance criteria. WOR-28 is now specifically blocked on **independent staff permission testing**, not another migration or seeding exercise. No real guest data or unapproved staff access.

The product goal remains a Workpeg-native hotel operating experience with precise reservations vs. in-house occupancy and separate maintenance/housekeeping readiness, using synthetic data until privacy and correctness are verified.
