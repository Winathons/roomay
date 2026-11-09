# WOR-58 — owner-operated `room_types` row persistence test

## Offline preparation status

`ui/dev_room_types_rows.py` is a standalone, development-only Workpeg UI. It
is not imported by `ui/main.py`, so its route and row controls are absent from
the release router. Compiling, mounting, refreshing, and automated tests issue
no Workpeg requests. The test harness forbids `fetch`. This implementation
does not create a table, read live data, or make a hosted write.

It targets only the already-existing `roomay_hotel_v1/room_types` table. It
does not create another table, enumerate the other eight hotel tables, or
read guests, reservations, stays, or service requests. The canonical contract
is taken from `contract_by_key()["room_types"]`: table namespace
`roomay_hotel_v1`; exact name `room_types`; permission `700`; metadata
`extra.contract = roomay.hotel.v1`; required columns `business_id:uuid`,
`entity_id:uuid`, `name:text`, and `capacity:number`, with their canonical
positions and no options/column metadata.

## Local inspection commands

From the repository root, the owner may compile the isolated screen offline:

```powershell
.\.venv\Scripts\workpeg.exe ui build ui/dev_room_types_rows.py
.\.venv\Scripts\python.exe -m unittest tests.test_dev_room_types_rows -v
```

For a later authenticated owner test, first confirm the current official
Workpeg 0.152.0 Windows dev-install prerequisites and use the reviewed
`tools/workpeg_serve_compat.py` MIME compatibility launcher with this source
file. The prior first-table instructions in `docs/wor-29-first-table-test.md`
describe the `--fake-cloud` dev-install prerequisites and printed HTTPS URL.
That server uses real Workpeg services; `fake-cloud` is not a mock. Do not
launch it as part of CI or this PR. In the same signed-in owner browser profile,
open the printed HTTPS origin and navigate to:

`/b/<owner-verified-Roomay-AI-development-business-UUID>/dev-room-types-rows`

The Workpeg route supplies business scope from its URL and the authenticated
session. The screen also requires the operator to enter that same UUID and
type `I VERIFIED ROOMAY AI OWNER CONTEXT`. These are safeguards against
operator mistakes, not authentication: SDK UI helpers do not expose the
current user's owner role or the business display name. The owner must
independently verify both in Workpeg before use. Stop if another business,
account, Peg installation, or environment is shown.

## Read-only inspection and row review

1. Click **Inspect existing table**. The screen calls `get_tables` for
   `roomay_hotel_v1`, requires exactly one visible `room_types` with permission
   `700` and the exact contract, then calls `get_table` by its native UUID and
   compares the returned schema. A missing or unreadable table, duplicates,
   malformed response, mismatched namespace/UUID/schema, 401, or 403 fails
   closed. The UI never claims that an empty readable list proves no hidden
   table exists.
2. Click **Read current rows**. The screen reads all pages in windows of 100,
   with a ten-page safety ceiling. Every row must carry a positive native row
   ID, nonempty opaque fingerprint, effective row permission `700`,
   `inherit_business_permission=true`, `inherit_individual_permissions=false`,
   valid application UUIDs and the URL business ID. Duplicate row
   IDs/fingerprints/entity IDs, malformed rows,
   cross-business data, or an incomplete page stop the flow. Only a small
   summary is shown. Inspect the complete inventory as the owner; the insert
   flow is offered only when the table is empty. Unexpected records are never
   overwritten or ignored.

## Separate owner approvals for future writes

The following writes have **not** been executed. Each requires a separate
owner decision in the isolated Roomay AI development business.

### Fictional insert approval

1. Verify the table and row-level permission grants in Workpeg's owner UI.
   The native row helper response does not enumerate individual row grants;
   the screen therefore requires the separate attestation
   `I VERIFIED NO ROW-LEVEL GRANTS` before it prepares or writes. This is an
   owner-operated check, not programmatic verification.
2. After reviewing the schema and complete empty inventory, click **Prepare
   fictional insert**. This is read-only and refreshes the schema and all rows.
3. Review the proposed values: the active URL business UUID; stable synthetic
   entity UUID `4a3e15b4-2df4-5a22-93c5-720d4eaa5801`; name
   `Roomay TEST Room Type (Fictional)`; capacity `2`.
4. Type `I UNDERSTAND SDK 401/403 REFRESH RETRY` and separately type
   `INSERT ROOMAY TEST ROOM TYPE`. The button performs another schema and
   complete-inventory read and requires the inventory to match the prepared
   empty state. Only then does it call `add_row` once at the application level.
5. A successful response is insufficient. The UI requires a native row ID,
   fingerprint and matching values, then performs a fresh full read and checks
   that the response agrees with the sole saved row.
6. The owner must manually reload the browser, click **Read current rows**, and
   verify the fictional row remains. Record only sanitized evidence; never
   include cookies, tokens, guest information, or unrelated row contents.

### Separate update approval

1. Repeat the row-level permission check and required attestation. After insert
   verification and manual reload, click **Prepare controlled
   capacity update**. Preparation succeeds only with exactly the single
   expected fictional row at capacity `2`.
2. Review its native row ID, fingerprint and proposed value change from
   capacity `2` to `3`. Type the SDK retry acknowledgement and separately type
   `UPDATE ROOMAY TEST CAPACITY ONLY`.
3. On click, schema and rows are read again. The native row ID, fingerprint,
   complete data and expected value must still match preparation. The UI
   builds a full replacement `data` object copied from the fresh row, changes
   only `capacity`, and calls `update_row` once at the application level.
4. The response must retain the native row ID, return a changed fingerprint
   and match every data field. A fresh complete read must then agree. The owner
   manually reloads and reads again to verify persistence.

There is no delete, rollback, bulk insert, automatic write, or automatic retry
after an uncertain result. A timeout, disconnect, denial, missing ID or
fingerprint, malformed response, or read-back mismatch locks writes in that
page session. On timeout the controller deliberately keeps the page busy
and locked, because the original protected request could still finish after the
UI stops waiting. Wait for the request to settle, then reconcile the actual
table and rows in a new owner-authenticated session before any further write.
Never attempt another call in the timed-out page, and do not click a write
again just because its response was lost.

## SDK and security limitations

The installed Workpeg SDK 0.152.0 compiler supports `get_tables(namespace)`,
`get_table(table_uuid)`, `get_rows(table_uuid, limit=..., offset=...)`,
`add_row(table_uuid, row)`, and `update_row(table_uuid, row_id, patch)`. The
runtime returns rows as a bare list; native `id` and `fingerprint` are
read-only. `update_row` is a PATCH of the row envelope, but the `data` object
is replaced as a whole, so all unrelated data is preserved in the update
payload.

The individual-permission GET endpoints are not exposed as purpose-built
`workpeg.*` row helpers in the compiler surface inspected here. The UI cannot
verify individual row grants programmatically; owner review is required. The
SDK's protected request helper may refresh authentication and retry once
after a 401/403. It exposes no per-call disable switch in the verified helper
contract. The controller never performs an application-level retry, but cannot
guarantee one network attempt. The owner must explicitly accept this behavior
before either write. Typed attestations are not role enforcement. Permission
`700`, owner identity, business identity, individual grants, actual data
retention after reload, and denial to other roles still require owner-run
verification. Mocked offline tests prove controller behavior only; they do
not prove Workpeg persistence, authorization, or production readiness.
