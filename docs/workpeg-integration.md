# Workpeg hotel integration contract (WOR-29)

This is the Phase A integration boundary for Roomay's real hotel data. The
owner reports that the Roomay AI development business has an existing
all nine canonical Workpeg tables at permission `700`, and has verified the
fictional Room 205 hotel/request workflow persists and appears through the
read-only receptionist. This hosted evidence is owner reported; Codex made no
live Workpeg calls. Non-owner staff permission behavior, guest access, writes
from the application and production integration remain unverified. Do not
modify or recreate the existing tables or records.

The historical `Unknown peg namespace 'roomay'` and `room_types` missing
observations are superseded by the owner's later development verification.
WOR-28 remains open until role permissions and all required persistence
criteria are completed. Do not switch Pegs, businesses, tokens, or releases
on speculation.

## Runtime boundary

`domain/workpeg_adapter.py` is a pure normalizer and contract validator. It has
no SDK dependency and no I/O. It converts native row envelopes to the existing
hotel and service-request records, calls the existing domain validators, and
keeps the native `row_id` and opaque `fingerprint` in a separate mapping.
Booking, check-in, assignment and request-transition rules remain in their
existing domain modules.

`ui/hotel_data.py` is the SDK transport and read-only receptionist application.
It compiles into the browser, where `workpeg.*` uses the authenticated session
and business ID from `/b/<business_id>/reception`. It loads on mount and through
an explicit refresh action. The route rejects malformed business context,
missing or duplicate tables, unsafe permissions, malformed pages,
cross-business rows, duplicate identities, incomplete records and inconsistent
hotel/service-request relationships before rendering the snapshot.

A successful read is labelled as a snapshot, not a lock. The route offers an
explicit stale marker. It does not confirm reservations: the documented SDK
has no transaction, unique constraint, conditional update or compare-and-swap
helper, so local eligibility cannot make a concurrency-safe booking.

## SDK 0.152.0 and official documentation evidence

The installed distribution was inspected at
`.venv/Lib/site-packages/workpeg/`:

| Evidence | Verified behavior |
| --- | --- |
| `ui/compiler/ast_parser.py`, `_WORKPEG_TABLE_HELPERS` | On the pinned 0.152.0 SDK, `get_tables([namespace])`; `get_table(uuid)`; `create_table(table)`; `update_table(uuid, patch)`; `delete_table(uuid)`; `get_rows(uuid, limit=..., offset=...)`; `get_row(uuid, row_id)`; `add_row(uuid, row)`; `add_rows(uuid, rows)`; `update_row(uuid, row_id, patch)`; `delete_row(uuid, row_id)` compile. Only `limit` and `offset` are accepted keywords for `get_rows`. |
| `ui/runtime/workpeg-runtime.js`, `wpGetTables` / `wpGetRows` | Calls are protected and scoped to the active URL business. Namespace is URL encoded. Row windows are sent as non-negative integer `limit`/`offset` values. |
| Official Tables & Rows documentation | A table is addressed by its returned UUID. `get_rows` returns a plain list ordered by descending position. Row `id` is a read-only integer and `fingerprint` is an opaque change marker. |
| Official Tables & Rows documentation | Table aliases are write-only and currently serve schema inheritance; they cannot resolve a runtime table UUID. Discovery therefore verifies namespace, exact name, permission and columns. |
| Official Tables & Rows documentation | `PATCH` is partial at the row level, but its `data` field replaces the whole object. `full_row_update` always preserves unrelated data. |
| Official Getting Started documentation | The compiler parses Python without executing it. A real authenticated local origin can reach production APIs; therefore this work does not run `--fake-cloud`. |

Official references:

- <https://developers.workpeg.com/docs/latest/tables/>
- <https://developers.workpeg.com/docs/latest/getting-started/>
- <https://developers.workpeg.com/docs/latest/reference/>

## Table contract

All nine tables are owner-only (`700`) and include a required canonical
`business_id` UUID in every row. Workpeg already scopes tables to a business;
the duplicated value is a fail-closed disclosure guard and is stripped before
domain validation.

| Namespace | Table | Stable alias for future owner-run provisioning | Domain identity |
| --- | --- | --- | --- |
| `roomay_hotel_v1` | `room_types` | `roomay-hotel-v1-room-types` | `entity_id` |
| `roomay_hotel_v1` | `rooms` | `roomay-hotel-v1-rooms` | `entity_id` |
| `roomay_hotel_v1` | `guests` | `roomay-hotel-v1-guests` | `entity_id` |
| `roomay_hotel_v1` | `reservations` | `roomay-hotel-v1-reservations` | `entity_id` |
| `roomay_hotel_v1` | `stays` | `roomay-hotel-v1-stays` | `entity_id` |
| `roomay_hotel_v1` | `stay_guests` | `roomay-hotel-v1-stay-guests` | `entity_id` |
| `roomay_hotel_v1` | `room_blocks` | `roomay-hotel-v1-room-blocks` | `entity_id` |
| `roomay_requests_v1` | `Roomay Service Requests` | `roomay-service-requests-v1` | `request_id` |
| `roomay_requests_v1` | `Roomay Service Request Audit` | `roomay-service-request-audit-v1` | `event_id` |

The exact column definitions are generated by `table_contracts()` from the
canonical hotel and service-request schemas. An authorized migration must use
those payloads and record every returned UUID. Runtime code must not assume an
alias will be returned.

## Failure and reconciliation contract

- A missing table means missing **or unreadable**. The adapter never creates it.
- Empty room types or rooms produce `empty_inventory=True`; no fixtures are
  substituted.
- All tables are read in windows of 100 until the first short list. A safety
  ceiling stops unbounded or inconsistent pagination.
- A row is rejected if its business differs from the active business, its
  native ID/fingerprint is missing, its application identity is duplicated,
  or its record fails the existing cross-table domain rules.
- Historical service requests retain their original persisted room association.
  A later legitimate room transfer may change the stay's current `room_id`
  without rewriting request history. The missing authoritative room-move audit
  contract is tracked under WOR-12; this read adapter does not invent one.
- A timed-out or failed mutation must be read back before any retry.
  `reconcile_write` distinguishes confirmed, not applied, conflict, malformed
  and missing outcomes. A changed fingerprint is evidence of change, not proof
  that this caller won a race.
- A trusted writer must serialize reservation confirmation and re-read the
  authoritative rows. Workpeg 0.152.0 documents no atomic uniqueness or CAS
  primitive, so the production concurrency mechanism remains an integration
  requirement, not an optimistic UI behavior.

## Remaining owner-run validation after first persistence proof

These steps are intentionally not performed by Codex or automated tests:

1. Confirm the approved `roomay` Peg is installed in the exact development
   business. Approval alone is not installation.
2. Use one authorized owner and one browser tab at
   `/b/<verified-business-uuid>/reception`.
3. Let the authenticated route load, then use Refresh records. Capture the exact
   status without exposing cookies, tokens, business IDs, or record data.
4. Preserve the existing owner-reported `room_types` table and fictional test
   row. Review the eight remaining schemas with the WOR-59 runbook; provision
   only one table at a time after separate owner approval.
5. For each approved table, verify native UUID, exact schema/permission,
   create-response/direct-GET/fresh-list agreement, reload persistence, and
   sanitized reconciliation after any uncertain result.
6. Verify role denial, row-level grants, cross-business isolation and trusted
   hotel identity mapping. Keep WOR-28, WOR-29 and WOR-8 In Progress until
   hosted acceptance criteria are complete.

## WOR-34 implementation

The receptionist route now consumes the transport arrays, retains native row
references outside domain records, and validates cross-table relationships
before rendering. It imports no fixture or demo module and keeps physical stays
distinct from reservations. See `docs/wor-34.md` for UI states, authorization
limits, and remaining live acceptance steps.

