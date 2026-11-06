# WOR-8 Phase A: offline hotel model

Implemented: pure Python validation and eligibility checks in `domain/hotel.py`,
declarative schema proposals in `domain/schema.py`, deterministic fictional records
in `domain/fixtures.py`, and automated tests. There is no database, network client,
seed command, table provisioning, authentication or write adapter. The starter UI
is unchanged. Python domain code is not compiled into the Peg UI or deployed as a
function; UI compilation verifies the existing scaffold only.

**WOR-8 remains In Progress.** Its hosted read/write acceptance criteria depend on
WOR-6 and are not satisfied by these checks. Service requests and incidents from
the larger issue are deferred; this phase covers inventory, bookings and presence.

## Verified SDK evidence (2026-11-06)

Authoritative reference: [Workpeg Tables documentation](https://developers.workpeg.com/docs/latest/tables/),
especially Column types, Rows, Permissions and workpeg helpers. The `latest` page
can change; the locally inspected installed distribution is `workpeg==0.149.1`.

Installed files under `workpeg/` inspected:

- `ui/compiler/ast_parser.py`, `_WORKPEG_TABLE_HELPERS` (around lines 148–160):
  recognizes `get_tables([namespace])`, `get_table(table_uuid)`,
  `create_table(table)`, `update_table(table_uuid, patch)`, `delete_table(table_uuid)`,
  `get_rows(table_uuid, limit=..., offset=...)`, `get_row(table_uuid, row_id)`,
  `add_row(table_uuid, row)`, `add_rows(table_uuid, rows)`,
  `update_row(table_uuid, row_id, patch)`, `delete_row(table_uuid, row_id)`.
- `ui/runtime/workpeg-runtime.js`, lines 530–632: implementations construct
  business-scoped URLs and use protected request helpers; row lists are arrays.
- `ui/app.py`, `_Workpeg`: Python is a compiler sentinel, not an executable Python
  table client. The sentinel alone does not enumerate all supported helpers.

The official column types are `text`, `number`, `boolean`, `datetime`, `currency`,
`country`, `teammate`, `uuid`, `file`, `mutable_select`, `many_to_many`, `recurrence`,
and deprecated `select`. There is no documented `foreign_key` or standalone `date`
column type. This proposal uses only text, number, boolean, uuid, datetime and
mutable_select. Date columns use `metadata: {type: "date"}`; timestamp columns use
`metadata: {type: "datetime"}`. Choice values are refs from `{ref, tag}` pairs.
Application validation restricts capacities/party sizes to positive integers.

Documented column ids may be custom strings. A table's remote `uuid` and a row's
read-only integer `id` differ from our `entity_id` UUID column. Row values go in
`data`, keyed by column id. `PATCH` **replaces the whole data object** when present.
Any later adapter must preserve all other data keys. `fingerprint` is a read-only
change marker; no compare-and-swap guarantee was established. No transaction,
unique constraint, foreign-key enforcement, index creation or atomic inventory
primitive is assumed. These are documentation/source findings, not live API tests.

## Minimum proposed business-scoped tables

Every table has required `entity_id: uuid`. All fields below are required except
those marked `?`. Full payload-shaped specifications are returned by
`proposed_tables()`; that function has no side effects. Initial proposed permission
is owner-only `700`, namespace `roomay_hotel_v1`, within the Roomay Peg's business.
WOR-6 must verify actual permission behavior before provisioning.

| Table | Fields besides entity_id | Associations / local constraints |
| --- | --- | --- |
| room_types | name: text; capacity: number | Positive integer capacity |
| rooms | number: text; room_type_id: uuid; enabled: boolean; housekeeping: mutable_select | Unique exact room number; type must exist; housekeeping = ready / dirty / cleaning / inspection |
| guests | display_name: text | Minimal fictional identity; names are not unique identifiers |
| reservations | guest_id: uuid; room_type_id: uuid; room_id?: uuid; arrival/departure: datetime(date); party_size: number; source/status: mutable_select | Booker need not be an occupant. source = advance / walk_in; status = pending_confirmation / confirmed / cancelled. Confirmed requires room assignment in Phase A |
| stays | reservation_id/room_id: uuid; checked_in_at: datetime; checked_out_at?: datetime; status: mutable_select | Matching confirmed reservation; one stay per reservation; checked_in / checked_out; one active stay per room |
| stay_guests | stay_id/guest_id: uuid; joined_at: datetime; left_at?: datetime | Registered physical occupants, unique stay/guest pair; timestamps within stay; total registered guests <= booked party size |
| room_blocks | room_id: uuid; start/end: datetime(date); reason: text; status: mutable_select | active / released; blocks are independent of occupancy and cleaning |

UUID references are application-level associations, not native relational columns.
Entity ids must be unique within each table. Local validation rejects dangling
references, unknown fields/statuses, noncanonical UUIDs, inconsistent checkout
timestamps, unregistered stays, over-capacity parties and conflicting confirmed
reservations. Capacity counts all registered guests for a stay in this minimal
model; occupant replacements/re-entry, split stays, room moves, group bookings,
unassigned room-type inventory and overbooking require later explicit workflows.

## Dates, conflicts and eligibility

- Booking and maintenance ranges are half-open `[start, end)` hotel-local dates.
  Two ranges overlap exactly when `a.start < b.end and b.start < a.end`.
  Departure on another booking's arrival is allowed. Zero-night, reversed,
  malformed and impossible calendar dates fail. Day-use stays are out of scope.
- Physical check-in/out and occupant timestamps require explicit UTC offsets.
  Eligibility takes an explicit hotel-local `today`, never the host clock. The
  future adapter must use the hotel's configured timezone and trusted server time.
- Only confirmed reservations hold inventory; pending requests may conflict and
  must remain Pending Confirmation until staff review. Cancelled records hold none
  and cannot check in. A walk-in follows the same reservation/confirmation rules;
  creating or confirming it does not create a stay or an occupant record.
- Check-in requires staff approval, confirmed matching assignment, an enabled room
  of the requested type, arrival <= today < departure, ready housekeeping, no active
  stay, no overlapping confirmed reservation and no overlapping active block.
  A reservation already used for any stay cannot be checked in again.
- In both allocation and check-in mode, a confirmed booking assigned to a different
  room returns `confirmed_reservation_assigned_elsewhere`. Checking its existing
  room remains valid subject to all other rules. Pending bookings may be evaluated
  for a new room, including first-time allocation without a tentative assignment.
  Eligibility never authorizes reassignment; an actual room change needs a separate
  authorized transition, which Phase A does not implement.
- For allocation, dirty/cleaning/inspection does not prohibit a future booking;
  readiness is checked at arrival. Active stays conservatively reject allocation
  even for a future range: expected departure is not actual checkout. This reduces
  availability in Phase A rather than silently treating an overdue guest as gone.
- Maintenance blocks may overlap a reservation or occupied room: this is a valid
  operational exception requiring staff action, not corrupt data. Room 205 is both
  occupied and blocked. Multiple blocks can coexist; any active overlapping block
  rejects eligibility. Released blocks do not block.
- Malformed/inconsistent snapshots fail validation before eligibility. The caller
  must not turn validation failures into availability. Results are reason codes,
  not transitions, locks, authentication decisions or persistence guarantees.
  `staff_approved=True` is an offline input, not evidence of a verified staff role.

## Fixtures and lookup

`synthetic_hotel()` returns fresh deterministic data: 10 rooms (201–210), two types,
three fictional guests, a future booking, a confirmed walk-in without a stay, one
active stay in 205 with a registered guest, dirty vacant 203 and blocked 205.
Fixture dates are fixed around November 6, 2026; they do not slide with today's
date. UUIDv5 labels use a synthetic-only namespace. These are in-memory dictionaries,
not Workpeg rows and not an idempotent remote seeder.

Later reads must page through the complete relevant business dataset, validate it,
then build in-memory lookup maps by entity_id, exact room number, reservation
room/date and active stays by room; maps are disposable, not a second database.
No server-side indexing/filtering facility beyond the documented helpers is
claimed. Partial pages, permission-filtered data and stale snapshots cannot prove
availability; the integration must establish complete authorized inventory access.

Identify a guest by internal UUID and an authorized registered stay association.
A display name, booking alone, caller ID or room QR is not proof of presence or
identity. Store no passport scans, contact information, payments or identity
documents in these fixtures. Before real data use, define hotel-approved retention
periods, lawful access and deletion/anonymization handling for linked records.
No legal retention duration is invented here; no scheduled deletion is implemented.

## Next integration steps, gated by WOR-6

1. In an explicitly authorized isolated business, prove fictional row create/read/
   update/reload, correct Peg/business scoping and negative permission tests.
2. Review these proposed fields and staff roles; verify date encoding, custom
   column ids, choices and schema responses on the actual service. Keep guests and
   occupants private; grant staff only approved operational access.
3. Implement the adapter with actual table UUID/row id discovery, full pagination,
   data-preserving updates, validation and explicit handling of partial failures.
   Verify idempotent seed identity/duplicate handling before any seed writes.
4. Establish an authoritative serialized confirmation/check-in workflow. Do not
   use client-side read/check/write as an atomic booking guarantee. If platform
   coordination remains unverified, keep requests Pending Confirmation and staff
   approval serialized; multi-user correctness must be demonstrated before release.
5. Verify authorized reservation-to-stay and registered-occupant creation,
   checkout making the room dirty, maintenance blocks on occupied rooms, recovery
   after partial writes, refresh persistence, stale state and concurrent requests.
6. Add service request/incident schemas under their approved scope. Demonstrate
   remaining WOR-8 acceptance criteria before claiming the issue complete.

No live Workpeg API, `--fake-cloud`, production records, credentials or billable AI
were used in Phase A. Reading public SDK docs and GitHub/Linear coordination is
separate from Workpeg service access.

## Verification

From repository root with the pinned SDK environment active:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q ui function domain tests
workpeg ui build ui/
workpeg doctor . --offline
git diff --check
```

CI runs the offline unit tests, syntax check and Workpeg UI compiler without secrets
or live service calls. No UI changes require screenshots in this phase.
