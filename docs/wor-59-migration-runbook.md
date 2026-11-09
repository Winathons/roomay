# WOR-59 — owner-reviewed Workpeg schema migration runbook

## Current status and safety boundary

The owner reports that the existing `roomay_hotel_v1/room_types` table has permission `700`, contains the fictional `Roomay TEST Room Type (Fictional)` at capacity 3, and was read, updated, read back and verified after an independent browser reload. This is owner-provided hosted evidence; this implementation made no Workpeg network request. The screen will only inspect and preserve `room_types`; it has no row operations, schema update or delete operation.

The new planner and UI are offline implementation only. No table was created by this change. The dev-only UI is isolated at `/b/<business_id>/dev-schema-migration` in its standalone artifact and is not imported into `ui/main.py`. Each future `create_table` request requires a new, separate owner approval. The status of a missing entry is **missing or unreadable** because Workpeg returns tables the caller can read; it cannot prove that an inaccessible matching table is absent.

Official Workpeg references: [Tables & Rows](https://developers.workpeg.com/docs/latest/tables/) and [Getting started](https://developers.workpeg.com/docs/latest/getting-started/). The installed 0.152.0 compiler source was checked for the table helper signatures. `get_tables([namespace])`, `get_table(table_uuid)` and `create_table(table)` are supported; create returns a table object with native UUID. The SDK UI compiler cannot invoke imported domain functions, so the compiled controller contains a compact contract mirror. Automated parity tests compare every generated table payload against `domain/workpeg_adapter.py::table_contracts()`.

## Canonical contracts

All contracts below come from `domain/workpeg_adapter.py::table_contracts()` via `domain/schema_migration.py::ordered_contracts()`. Positions, required flags, choices and date/datetime metadata are shown exactly. Each table is owner-only (`700`) initially. `business_id` is required in all tables at position 500. Each table's listed fields follow it. `uuid` references are application-level associations; Workpeg does not enforce them as foreign keys.

### `room_types`

- Namespace: `roomay_hotel_v1`
- Stable alias: `roomay-hotel-v1-room-types` (write-only in Workpeg responses)
- Permission: `700`
- Table metadata: `{'extra': {'contract': 'roomay.hotel.v1'}}`
- Relationships: Existing table; preserve its verified native UUID and fictional test row. Rooms reference it.

| Column ID | Type | Required | Position | Select choices | Field metadata |
|---|---|---:|---:|---|---|
| `business_id` | `uuid` | yes | 500 | — | `{}` |
| `entity_id` | `uuid` | yes | 1000 | — | `{}` |
| `name` | `text` | yes | 2000 | — | `{}` |
| `capacity` | `number` | yes | 3000 | — | `{}` |

### `rooms`

- Namespace: `roomay_hotel_v1`
- Stable alias: `roomay-hotel-v1-rooms` (write-only in Workpeg responses)
- Permission: `700`
- Table metadata: `{'extra': {'contract': 'roomay.hotel.v1'}}`
- Relationships: room_type_id references room_types.entity_id.

| Column ID | Type | Required | Position | Select choices | Field metadata |
|---|---|---:|---:|---|---|
| `business_id` | `uuid` | yes | 500 | — | `{}` |
| `entity_id` | `uuid` | yes | 1000 | — | `{}` |
| `number` | `text` | yes | 2000 | — | `{}` |
| `room_type_id` | `uuid` | yes | 3000 | — | `{}` |
| `enabled` | `boolean` | yes | 4000 | — | `{}` |
| `housekeeping` | `mutable_select` | yes | 5000 | ready → ready, dirty → dirty, cleaning → cleaning, inspection → inspection | `{}` |

### `guests`

- Namespace: `roomay_hotel_v1`
- Stable alias: `roomay-hotel-v1-guests` (write-only in Workpeg responses)
- Permission: `700`
- Table metadata: `{'extra': {'contract': 'roomay.hotel.v1'}}`
- Relationships: Reservations and stay_guests reference guest entity IDs.

| Column ID | Type | Required | Position | Select choices | Field metadata |
|---|---|---:|---:|---|---|
| `business_id` | `uuid` | yes | 500 | — | `{}` |
| `entity_id` | `uuid` | yes | 1000 | — | `{}` |
| `display_name` | `text` | yes | 2000 | — | `{}` |

### `reservations`

- Namespace: `roomay_hotel_v1`
- Stable alias: `roomay-hotel-v1-reservations` (write-only in Workpeg responses)
- Permission: `700`
- Table metadata: `{'extra': {'contract': 'roomay.hotel.v1'}}`
- Relationships: guest_id references guests; room_type_id references room_types; optional room_id references rooms.

| Column ID | Type | Required | Position | Select choices | Field metadata |
|---|---|---:|---:|---|---|
| `business_id` | `uuid` | yes | 500 | — | `{}` |
| `entity_id` | `uuid` | yes | 1000 | — | `{}` |
| `guest_id` | `uuid` | yes | 2000 | — | `{}` |
| `room_type_id` | `uuid` | yes | 3000 | — | `{}` |
| `room_id` | `uuid` | no | 4000 | — | `{}` |
| `arrival` | `datetime` | yes | 5000 | — | `{'type': 'date'}` |
| `departure` | `datetime` | yes | 6000 | — | `{'type': 'date'}` |
| `party_size` | `number` | yes | 7000 | — | `{}` |
| `source` | `mutable_select` | yes | 8000 | advance → advance, walk_in → walk_in | `{}` |
| `status` | `mutable_select` | yes | 9000 | pending_confirmation → pending_confirmation, confirmed → confirmed, cancelled → cancelled | `{}` |

### `stays`

- Namespace: `roomay_hotel_v1`
- Stable alias: `roomay-hotel-v1-stays` (write-only in Workpeg responses)
- Permission: `700`
- Table metadata: `{'extra': {'contract': 'roomay.hotel.v1'}}`
- Relationships: reservation_id references reservations and room_id references rooms. A stay represents physical occupancy.

| Column ID | Type | Required | Position | Select choices | Field metadata |
|---|---|---:|---:|---|---|
| `business_id` | `uuid` | yes | 500 | — | `{}` |
| `entity_id` | `uuid` | yes | 1000 | — | `{}` |
| `reservation_id` | `uuid` | yes | 2000 | — | `{}` |
| `room_id` | `uuid` | yes | 3000 | — | `{}` |
| `checked_in_at` | `datetime` | yes | 4000 | — | `{'type': 'datetime'}` |
| `checked_out_at` | `datetime` | no | 5000 | — | `{'type': 'datetime'}` |
| `status` | `mutable_select` | yes | 6000 | checked_in → checked_in, checked_out → checked_out | `{}` |

### `stay_guests`

- Namespace: `roomay_hotel_v1`
- Stable alias: `roomay-hotel-v1-stay-guests` (write-only in Workpeg responses)
- Permission: `700`
- Table metadata: `{'extra': {'contract': 'roomay.hotel.v1'}}`
- Relationships: stay_id references stays and guest_id references guests; models registered occupants.

| Column ID | Type | Required | Position | Select choices | Field metadata |
|---|---|---:|---:|---|---|
| `business_id` | `uuid` | yes | 500 | — | `{}` |
| `entity_id` | `uuid` | yes | 1000 | — | `{}` |
| `stay_id` | `uuid` | yes | 2000 | — | `{}` |
| `guest_id` | `uuid` | yes | 3000 | — | `{}` |
| `joined_at` | `datetime` | yes | 4000 | — | `{'type': 'datetime'}` |
| `left_at` | `datetime` | no | 5000 | — | `{'type': 'datetime'}` |

### `room_blocks`

- Namespace: `roomay_hotel_v1`
- Stable alias: `roomay-hotel-v1-room-blocks` (write-only in Workpeg responses)
- Permission: `700`
- Table metadata: `{'extra': {'contract': 'roomay.hotel.v1'}}`
- Relationships: room_id references rooms; blocks availability for its dates.

| Column ID | Type | Required | Position | Select choices | Field metadata |
|---|---|---:|---:|---|---|
| `business_id` | `uuid` | yes | 500 | — | `{}` |
| `entity_id` | `uuid` | yes | 1000 | — | `{}` |
| `room_id` | `uuid` | yes | 2000 | — | `{}` |
| `start` | `datetime` | yes | 3000 | — | `{'type': 'date'}` |
| `end` | `datetime` | yes | 4000 | — | `{'type': 'date'}` |
| `reason` | `text` | yes | 5000 | — | `{}` |
| `status` | `mutable_select` | yes | 6000 | active → active, released → released | `{}` |

### `Roomay Service Requests`

- Namespace: `roomay_requests_v1`
- Stable alias: `roomay-service-requests-v1` (write-only in Workpeg responses)
- Permission: `700`
- Table metadata: `{'extra': {'contract': 'roomay.service_requests.v1'}}`
- Relationships: hotel_id is a trusted business-to-hotel mapping; stay_id, room_id and guest_id associate a verified request context.

| Column ID | Type | Required | Position | Select choices | Field metadata |
|---|---|---:|---:|---|---|
| `business_id` | `uuid` | yes | 500 | — | `{}` |
| `request_id` | `uuid` | yes | 1000 | — | `{}` |
| `idempotency_key` | `text` | yes | 2000 | — | `{}` |
| `hotel_id` | `uuid` | yes | 3000 | — | `{}` |
| `stay_id` | `uuid` | yes | 4000 | — | `{}` |
| `room_id` | `uuid` | yes | 5000 | — | `{}` |
| `guest_id` | `uuid` | yes | 6000 | — | `{}` |
| `origin` | `mutable_select` | yes | 7000 | guest → guest, reception_desk → reception_desk, phone → phone, staff → staff | `{}` |
| `category` | `mutable_select` | yes | 8000 | unknown → unknown, extra_towels → extra_towels, linen → linen, room_cleaning → room_cleaning, toiletries → toiletries, plumbing → plumbing, electrical → electrical, air_conditioning → air_conditioning, room_equipment → room_equipment, room_service → room_service, dining → dining, minibar → minibar, transport → transport, wake_up_call → wake_up_call, billing_question → billing_question, general_help → general_help | `{}` |
| `category_detail` | `text` | yes | 9000 | — | `{}` |
| `department` | `mutable_select` | yes | 10000 | housekeeping → housekeeping, maintenance → maintenance, food_and_beverage → food_and_beverage, reception → reception | `{}` |
| `description` | `text` | yes | 11000 | — | `{}` |
| `urgency` | `mutable_select` | yes | 12000 | low → low, normal → normal, high → high, urgent → urgent | `{}` |
| `status` | `mutable_select` | yes | 13000 | received → received, assigned → assigned, acknowledged → acknowledged, in_progress → in_progress, resolved → resolved, reopened → reopened, cancelled → cancelled, escalated → escalated | `{}` |
| `assigned_staff_id` | `text` | no | 14000 | — | `{}` |
| `triage_required` | `boolean` | yes | 15000 | — | `{}` |
| `sensitive` | `boolean` | yes | 16000 | — | `{}` |
| `created_at` | `datetime` | yes | 17000 | — | `{'type': 'datetime'}` |
| `updated_at` | `datetime` | yes | 18000 | — | `{'type': 'datetime'}` |
| `received_at` | `datetime` | yes | 19000 | — | `{'type': 'datetime'}` |
| `acknowledge_by` | `datetime` | yes | 20000 | — | `{'type': 'datetime'}` |
| `due_at` | `datetime` | yes | 21000 | — | `{'type': 'datetime'}` |
| `assigned_at` | `datetime` | no | 22000 | — | `{'type': 'datetime'}` |
| `acknowledged_at` | `datetime` | no | 23000 | — | `{'type': 'datetime'}` |
| `in_progress_at` | `datetime` | no | 24000 | — | `{'type': 'datetime'}` |
| `resolved_at` | `datetime` | no | 25000 | — | `{'type': 'datetime'}` |
| `reopened_at` | `datetime` | no | 26000 | — | `{'type': 'datetime'}` |
| `cancelled_at` | `datetime` | no | 27000 | — | `{'type': 'datetime'}` |
| `escalated_at` | `datetime` | no | 28000 | — | `{'type': 'datetime'}` |
| `version` | `number` | yes | 29000 | — | `{}` |
| `last_event_id` | `uuid` | yes | 30000 | — | `{}` |
| `last_operation_signature` | `text` | yes | 31000 | — | `{}` |

### `Roomay Service Request Audit`

- Namespace: `roomay_requests_v1`
- Stable alias: `roomay-service-request-audit-v1` (write-only in Workpeg responses)
- Permission: `700`
- Table metadata: `{'extra': {'contract': 'roomay.service_requests.v1'}}`
- Relationships: request_id references Roomay Service Requests; operation_id and event_id are application identities.

| Column ID | Type | Required | Position | Select choices | Field metadata |
|---|---|---:|---:|---|---|
| `business_id` | `uuid` | yes | 500 | — | `{}` |
| `event_id` | `uuid` | yes | 1000 | — | `{}` |
| `operation_id` | `uuid` | yes | 2000 | — | `{}` |
| `operation_signature` | `text` | yes | 3000 | — | `{}` |
| `request_id` | `uuid` | yes | 4000 | — | `{}` |
| `hotel_id` | `uuid` | yes | 5000 | — | `{}` |
| `sequence` | `number` | yes | 6000 | — | `{}` |
| `event_type` | `mutable_select` | yes | 7000 | created → created, status_changed → status_changed, triaged → triaged | `{}` |
| `from_status` | `text` | no | 8000 | — | `{}` |
| `to_status` | `mutable_select` | yes | 9000 | received → received, assigned → assigned, acknowledged → acknowledged, in_progress → in_progress, resolved → resolved, reopened → reopened, cancelled → cancelled, escalated → escalated | `{}` |
| `actor_id` | `text` | yes | 10000 | — | `{}` |
| `actor_kind` | `mutable_select` | yes | 11000 | guest → guest, staff → staff | `{}` |
| `actor_department` | `mutable_select` | no | 12000 | housekeeping → housekeeping, maintenance → maintenance, food_and_beverage → food_and_beverage, reception → reception | `{}` |
| `occurred_at` | `datetime` | yes | 13000 | — | `{'type': 'datetime'}` |
| `reason` | `text` | no | 14000 | — | `{}` |
| `commit_state` | `mutable_select` | yes | 15000 | pending → pending, committed → committed | `{}` |

## Recommended creation order and prerequisites

1. `rooms` — requires the already-existing `room_types` table.
2. `guests` — independent lookup record schema.
3. `reservations` — references guests and room types; optional assigned room references rooms.
4. `stays` — requires reservations and rooms; only stays represent physical check-in.
5. `stay_guests` — requires stays and guests for registered-occupant association.
6. `room_blocks` — requires rooms; maintenance blocks remain separate from occupancy and housekeeping.
7. `Roomay Service Requests` — requires a trusted hotel identity mapping and verified stay/room/guest references.
8. `Roomay Service Request Audit` — follows service-request creation and references the canonical request identifier.

This order expresses application prerequisites, not Workpeg foreign-key constraints. The current canonical schema has no hotel table. Service-request rows carry `hotel_id`; a trusted single-hotel-per-business mapping is still required. Do not infer a hotel's UUID from a browser-supplied value, and do not claim multi-hotel isolation until a trusted mapping/schema contract exists.

## Planner outcomes

The pure planner compares both namespace inventories to all nine canonical contracts. It reports `existing_compatible`, `missing_or_unreadable`, `required_existing_table_missing`, `duplicate`, `incorrect_permissions`, `incorrect_columns`, `incorrect_metadata`, `incompatible_table`, `inventory_unknown`, or an unexpected table list. It does not propose repairs. Any malformed, duplicate, incompatible or unexpected table blocks all creation until an owner resolves the ambiguity. A missing `room_types` table blocks migration and is never eligible for creation.

A missing table becomes eligible only after both namespace responses are structurally valid, existing records match the canonical contract, no duplicate/unexpected/conflicting table exists, and the owner separately attests in the Workpeg dashboard that the exact selected table is absent. The attestation is an operator safeguard, not authentication or proof of permission.

## Owner-operated procedure — only after PR review and separate approval

**No creation is authorized by this PR.** Do not run this procedure until the PR is reviewed and the owner separately approves the exact single table to create.

1. Privately verify the signed-in owner account, Roomay AI development business UUID, approved `roomay` Peg installation, and URL business context. The UI SDK helper uses authenticated session and active `/b/<business_id>/` route; it does not expose the current user's owner role or prove the business display name.
2. In the Workpeg owner dashboard, inspect both namespaces and verify the selected name is truly absent, including hidden/inaccessible records and aliases. Confirm the existing `room_types` UUID/schema/permission and its fictional test row remain unchanged. Check owner-only table permissions and any individual grants.
3. From the repo root, with the reviewed Workpeg 0.152.0 Windows compatibility launcher and prerequisites already verified, the owner may start the isolated source route (this command is intentionally not run by CI or this change):

   ```powershell
   & "..\.venv\Scripts\python.exe" "tools\workpeg_serve_compat.py" "ui/dev_schema_migration.py" --fake-cloud
   ```

   `--fake-cloud` uses a real Workpeg origin; it is not a mock. Use only the isolated Roomay AI development business, same signed-in owner browser profile and trusted HTTPS origin. Do not bypass TLS or use tokens.
4. Navigate to `/b/<verified-business-UUID>/dev-schema-migration`. Enter the verified UUID and exact owner context attestation. Click **Inspect both namespaces**. Review existing compatible tables, native UUIDs, missing-or-unreadable entries, blockers and unexpected tables. A successful readable inventory does not establish absence of inaccessible tables.
5. Select exactly one of the eight remaining names. Independently verify that exact name is absent in Workpeg, then type `I VERIFIED THIS TABLE IS ABSENT: <exact table name>`. Click **Prepare selected schema** and review the complete on-screen payload: alias, namespace, permission `700`, metadata, every column ID/type/required flag/position, select choices and datetime metadata. Preparation is read-only and repeats both namespace reads plus direct GET for each compatible existing table.
6. Only after a separate explicit owner decision for this one table, acknowledge the SDK behavior by typing `I UNDERSTAND SDK 401/403 REFRESH RETRY`, type `CREATE ONLY: <exact table name>`, and click the create button once. The controller re-reads and compares the inventory and only then calls `workpeg.create_table` once at the application layer.
7. Success requires a valid create response/native UUID, direct `get_table(uuid)` with matching schema/permission, and a fresh listing from both namespaces containing exactly that matching table. The UI reports the native UUID and sanitized status. No rows are created.
8. Manually reload the browser and click **Inspect both namespaces** again. Verify the new table is still present and `room_types` retains its same UUID, schema and row. Only then may the owner separately approve preparing another single table. Do not run a batch or unattended sequence.

## Expected states and uncertain outcomes

- **Read-only success:** both namespace inventories parsed; every existing expected table validates against its full contract and direct GET; missing entries are explicitly “missing or unreadable”; owner review still required.
- **Blocked:** 401 authentication, 403 access denied, malformed/incomplete response, duplicate table/UUID, wrong namespace, permission/schema/metadata mismatch, unexpected table, missing `room_types`, or changed inventory. No create is attempted.
- **Create success:** response, direct GET and fresh namespace listing agree on table name, namespace, alias-independent canonical schema, permission and native UUID.
- **Uncertain create:** timeout, disconnect, malformed response, direct read-back failure, or fresh-list mismatch after POST. The UI locks and does not retry, delete or roll back. Wait for any request to settle; inspect through a separate owner-reviewed session. Preserve any created table. Reconcile by native UUID, exact name/schema/permission and owner dashboard before any further action. Never retry just because the response was lost.

SDK 0.152.0 protected helpers can refresh authentication and retry after a 401/403; the table helper has no verified per-call switch to disable it. The UI requires acknowledgment, but cannot guarantee one HTTP attempt. Owner approval must include this limitation.

## Later fictional data and application integration

After all schemas are separately reviewed and created, a distinct owner-approved data-seeding plan may create only clearly fictional development records using stable Roomay entity UUIDs. Verify every row's native Workpeg ID and fingerprint, row permission inheritance and business_id, then read back and reload. Do not seed records in this migration UI.

The receptionist's read-only adapter consumes `rooms`, `room_types`, `guests`, `reservations`, `stays`, `stay_guests`, `room_blocks`, and request records through `domain/workpeg_adapter.py`; relationship checks remain in the domain validators. Service-request workflows consume request and audit tables through their canonical contracts. No receptionist or service-request writes are enabled by this PR. Room/stay/guest UUID links are application-validated, not platform foreign keys.

## Permissions and production gates still required

All new tables start at `700`, which is owner-only. Before hotel staff can use them, the owner must decide and verify least-privilege read/write grants per role and table, including any row-level grants. The migration UI cannot inspect individual permission listings with a purpose-built compiler helper. Verify denial for nonmembers, guests, unrelated staff and wrong-business contexts; verify guest profiles and request descriptions do not leak. Free-text service-request descriptions may contain personal information, so grant/read models must treat them as sensitive. Reservation/check-in operations still require trusted server-side authorization, serialization/concurrency guarantees and reconciliation. These tests and live permission checks are separate acceptance gates.

The planner and compiled tests are offline evidence only. They do not prove hosted creation, current permission state, staff denial, persistence, authentication correctness, atomicity, or production readiness. No Workpeg request or hosted write was made while implementing WOR-59.
