# WOR-29 — Roomay Workpeg schema provisioning plan

**Status: prepared offline; no schema or row writes were performed.** This
document and `domain/schema_provisioning.py` produce reviewable plans and
validate mock/read-back responses. They do not call Workpeg or expose a
provisioning route. Workpeg remains the only intended operational database.
The narrower first-table, owner-operated procedure is documented in
[WOR-29 Phase B](wor-29-first-table-test.md); it is a separate dev-only
artifact and does not alter the release router.

## Current evidence and remaining gate

The owner reports that the Roomay receptionist page now renders in the Roomay
AI development business and Chrome Network shows
`GET /v1/businesses/{business_id}/tables/?namespace=roomay_hotel_v1` returning
HTTP 200. The UI then reports that `room_types` is missing or unreadable and
that it did not attempt provisioning. This resolves the prior namespace
rejection for table discovery; it does **not** establish table creation,
row-write, refresh-persistence, or permission behavior. This report uses the
owner's observation; Codex made no Workpeg API call.

Workpeg's Peg UI helpers read the active business from `/b/<business_id>/...`,
send the authenticated session, and attach the calling Peg's `Peg-Namespace`
header. The installed 0.152.0 compiler recognizes `get_tables([namespace])`,
`get_table(table_uuid)`, `create_table(table)`, `get_rows(table_uuid, limit,
offset)`, `add_row(table_uuid, row)`, and `update_row(table_uuid, row_id,
patch)`. The official docs specify that `get_tables` returns readable tables,
and `create_table` returns the created table including its native UUID. These
are supported helpers; no custom endpoint is needed. The local code still
cannot prove that the selected URL belongs to Roomay AI or that the signed-in
caller is the owner. The owner must verify both before an authorized write.

References: [Workpeg Tables & Rows](https://developers.workpeg.com/docs/latest/tables/)
and [Getting started / development business](https://developers.workpeg.com/docs/latest/getting-started/).

## Exact proposed schema

The canonical payload source is `domain.workpeg_adapter.table_contracts()`;
it composes `domain/schema.py` and `domain/service_request_schema.py`. All nine
tables start with permission string `"700"` (owner read/write/share; business
and public digits zero), use a stable custom column ID equal to the listed
field name, and use table metadata
`{"extra":{"contract":"roomay.hotel.v1"}}` or
`{"extra":{"contract":"roomay.service_requests.v1"}}` as appropriate.
Every table also has required `business_id: uuid` at position 500. Remaining
columns follow the order below at positions 1000, 2000, and so on. All fields
are required unless marked `?`. Mutable-select `ref` values equal their `tag`
values; rows store the ref string.

### Hotel operations — namespace `roomay_hotel_v1`

| Table | Ordered columns after `business_id` |
| --- | --- |
| `room_types` | `entity_id: uuid`, `name: text`, `capacity: number` |
| `rooms` | `entity_id: uuid`, `number: text`, `room_type_id: uuid`, `enabled: boolean`, `housekeeping: mutable_select[ready, dirty, cleaning, inspection]` |
| `guests` | `entity_id: uuid`, `display_name: text` |
| `reservations` | `entity_id: uuid`, `guest_id: uuid`, `room_type_id: uuid`, `room_id: uuid?`, `arrival: datetime(date)`, `departure: datetime(date)`, `party_size: number`, `source: mutable_select[advance, walk_in]`, `status: mutable_select[pending_confirmation, confirmed, cancelled]` |
| `stays` | `entity_id: uuid`, `reservation_id: uuid`, `room_id: uuid`, `checked_in_at: datetime(datetime)`, `checked_out_at: datetime(datetime)?`, `status: mutable_select[checked_in, checked_out]` |
| `stay_guests` | `entity_id: uuid`, `stay_id: uuid`, `guest_id: uuid`, `joined_at: datetime(datetime)`, `left_at: datetime(datetime)?` |
| `room_blocks` | `entity_id: uuid`, `room_id: uuid`, `start: datetime(date)`, `end: datetime(date)`, `reason: text`, `status: mutable_select[active, released]` |

### Guest service operations — namespace `roomay_requests_v1`

| Table | Ordered columns after `business_id` |
| --- | --- |
| `Roomay Service Requests` | `request_id: uuid`, `idempotency_key: text`, `hotel_id: uuid`, `stay_id: uuid`, `room_id: uuid`, `guest_id: uuid`, `origin: mutable_select[guest, reception_desk, phone, staff]`, `category: mutable_select[unknown, extra_towels, linen, room_cleaning, toiletries, plumbing, electrical, air_conditioning, room_equipment, room_service, dining, minibar, transport, wake_up_call, billing_question, general_help]`, `category_detail: text`, `department: mutable_select[housekeeping, maintenance, food_and_beverage, reception]`, `description: text`, `urgency: mutable_select[low, normal, high, urgent]`, `status: mutable_select[received, assigned, acknowledged, in_progress, resolved, reopened, cancelled, escalated]`, `assigned_staff_id: text?`, `triage_required: boolean`, `sensitive: boolean`, `created_at: datetime(datetime)`, `updated_at: datetime(datetime)`, `received_at: datetime(datetime)`, `acknowledge_by: datetime(datetime)`, `due_at: datetime(datetime)`, `assigned_at: datetime(datetime)?`, `acknowledged_at: datetime(datetime)?`, `in_progress_at: datetime(datetime)?`, `resolved_at: datetime(datetime)?`, `reopened_at: datetime(datetime)?`, `cancelled_at: datetime(datetime)?`, `escalated_at: datetime(datetime)?`, `version: number`, `last_event_id: uuid`, `last_operation_signature: text` |
| `Roomay Service Request Audit` | `event_id: uuid`, `operation_id: uuid`, `operation_signature: text`, `request_id: uuid`, `hotel_id: uuid`, `sequence: number`, `event_type: mutable_select[created, status_changed, triaged]`, `from_status: text?`, `to_status: mutable_select[received, assigned, acknowledged, in_progress, resolved, reopened, cancelled, escalated]`, `actor_id: text`, `actor_kind: mutable_select[guest, staff]`, `actor_department: mutable_select[housekeeping, maintenance, food_and_beverage, reception]?`, `occurred_at: datetime(datetime)`, `reason: text?`, `commit_state: mutable_select[pending, committed]` |

The seven hotel tables do **not** contain `hotel_id`. They are safe only for a
single hotel per Workpeg business under the current model. The Workpeg business
scope plus a required per-row `business_id` guards business mix-ups; it does not
isolate multiple hotels within one business. Service-request `hotel_id` fields
do not solve that gap for rooms, reservations, stays, or guests. Do not claim
multi-hotel isolation until a trusted hotel-to-business mapping and matching
schema migration are designed and reviewed.

UUID columns are application-level references, not Workpeg foreign keys.
Workpeg accepts `text`, `number`, `boolean`, `uuid`, `datetime`, and
`mutable_select` from these proposals. There is no separate `date` type: the
proposal uses `datetime` plus metadata `{"type":"date"}` for hotel-local
calendar dates, and `{"type":"datetime"}` for instants. Workpeg does not
enforce the domain's positive-integer capacity/party-size rules because these
number columns have no server-side minimum constraint. Table aliases are
write-only and not returned; the provisioning code uses exact namespace/name
matching and records the returned table UUID instead.

## Contract checks and discrepancies addressed

- `domain/schema.proposed_tables()` previously emitted permission as integer
  `700`; Workpeg documents table permission as a three-character string. It now
  emits `"700"`, matching the service schema and read adapter.
- The pure adapter now checks exact table/column metadata, names, positions,
  required flags, supported types, options, and mutable-select ref/tag choices.
- The compiled read-only adapter now mirrors these checks. Compiled fixtures
  assert parity with the pure contract, including date metadata and choice lists.
- The adapter does not rely on aliases being returned by Workpeg.

The hosted API's exact normalization of custom IDs, date metadata, mutable
choice refs, aliases, and `"700"` has not been verified by table creation in
the Roomay AI business. The first owner provisioning attempt must stop if any
read-back differs from these definitions; do not broaden the validator to fit
an unexpected response without reviewing the contract.

## Read-only planning and creation verification

`prepare_provisioning_plan()` requires a canonical explicit target business ID,
matching active URL business ID, Peg namespace exactly `roomay`, and successful
list-shaped responses for both table namespaces. It reports existing native
UUIDs, missing table keys, or a blocked state. Any duplicate, incompatible
table, wrong namespace, or unreadable inventory blocks **all** proposed creates
in that plan. A ready plan has `writes_authorized=False`; it only returns
payloads for a human to review. No SDK client is imported by this module.

For any future separately authorized owner-run table operation, the proposed
sequence is:

1. Verify the signed-in account, Roomay AI business, and exact active business
   UUID in the Workpeg browser. Confirm the build/manifest namespace is
   `roomay`; the Peg namespace header is attached by the SDK. A matching string
   passed to an offline planner is not authentication.
2. Call `workpeg.get_tables("roomay_hotel_v1")` and
   `workpeg.get_tables("roomay_requests_v1")` with the owner session. A failed
   or malformed response means unknown inventory, not missing tables.
3. Review the complete offline plan. Create **one missing table at a time** via
   `workpeg.create_table(payload)` with permission `"700"`. Never update, delete,
   replace, or seed from compilation, mount, startup, CI, or the release UI.
4. Save each returned table UUID in the redacted operator record. Immediately
   verify it with `workpeg.get_table(uuid)` and a fresh `get_tables(namespace)`
   result. Require exact identity, permission, all columns/options/metadata,
   exactly one namespace/name match, and the same returned UUID. Only then may
   the owner review the next create payload.
5. Stop on any failed response, mismatch, duplicate, timeout, or incomplete
   read-back. Do not retry a create whose outcome is uncertain. After the
   request settles, a fresh inventory may show whether it exists; an owner must
   reconcile that result before any new plan is approved.

Provisioning is nine independent table creates, not an atomic transaction. If
only some tables were created, leave them in place. Re-list both namespaces,
validate each existing table, and generate a new plan for only the missing
tables. Never automatically roll back by deleting tables: that could destroy
unknown rows. A duplicate, permission mismatch, or partial schema requires
manual owner review; the planner proposes no writes while blocked. A successful
`get_tables` response can only show tables the caller may read, so the owner
must use the table-owning account and confirm that no hidden/unreadable table
could collide with the planned names.

Table permission `700` initially grants the owner read/write/share and grants
neither business-wide nor public access. It does not prove the absence of
separate individual grants. Check the owner account and individual permission
state before adding test rows. Do not change permissions to make a test pass.

## First fictional room-row test — separately authorized later

`first_fictional_room_records(business_id)` creates deterministic payloads in
memory only, with `writes_authorized=False`:

1. Search the complete `room_types` row list for the deterministic entity ID or
   name. If absent, create one fictional `Roomay WOR-29 Fictional Single`
   room type with capacity 1. Read it back and record the Workpeg integer row
   ID and fingerprint separately from the Roomay UUID.
2. Search the full `rooms` list for its deterministic entity ID or logical room
   number `WOR29-201`. Only if absent, create one enabled fictional room linked
   to the room type's Roomay entity UUID, with housekeeping `ready`. Use the
   same explicit owner-only row inheritance settings in the plan. Read it back.
3. Reload the browser and confirm both native row IDs, entity IDs, values, and
   fingerprints. Repeat the list/read, without creating duplicates.
4. Only after a separate owner approval, change the synthetic room's
   `housekeeping` field from `ready` to `dirty`, preserving the complete
   existing row `data` object. Read the row back, reload, and verify the new
   fingerprint and value.
5. Use a second authorized test account to confirm read/write denial without
   changing the table's `700` permission. Record whether the denial is actually
   observed; do not treat a filtered list as proof that no table exists.

The SDK's `PATCH` replaces the entire `data` object when that field is sent, so
the status test must read/merge/preserve all unrelated values. Row fingerprints
are opaque change markers, not conditional-write/CAS tokens. A failed write or
timeout remains uncertain until read-back reconciliation; never blindly retry.
There is no rollback guarantee for a created row or table. No guest or real
hotel records belong in this first persistence check.

## Offline evidence and remaining Workpeg-side work

The offline tests use deterministic synthetic table responses and a
test-only `MockWorkpeg`; they cover correct/missing/duplicate tables, bad
namespace and business context, permission and column mismatch, partial
creation recovery, uncertain writes, duplicate fictional rows, and failed
read-back. They do not call Workpeg and are not proof of hosted persistence.

Owner approval is still required before any `create_table`, `add_row`, or
`update_row` call. WOR-28 and WOR-29 remain In Progress until the owner proves
table schema create/read-back, fictional row create/read/update/reload, and
second-account permission denial in the selected Roomay AI development
business. This plan does not resolve the single-hotel-per-business limitation,
staff permission deployment, atomic booking/checkout, or Workpeg concurrency.
