# WOR-34 receptionist request-action boundary

## Current behavior

The native Reception route in `ui/hotel_data.py` reads and validates the
business-scoped Workpeg hotel, request and audit tables. Request selection
projects the same validated snapshot into the detail panel. **The route remains
read-only:** the detail panel shows Assign, Acknowledge, Mark in progress and
Resolve as unavailable, and its Refresh status control calls the existing full
snapshot loader. The refresh does not write and is not an authorization check.

The panel does not accept a staff role, actor, business id, department or
permission claim from browser state. It has no callback to a writer. A failed
refresh continues through the existing loading/access-denied/unavailable UI;
it never changes the displayed status optimistically.

## Reusable contracts already in the repository

- `domain/service_requests.py::transition_request` owns the canonical lifecycle,
  department rules, assignment validation, transition guards, operation IDs,
  idempotency and audit event planning.
- `domain/staff_actions.py::StaffActionGateway.prepare` consumes an opaque
  session proof through injected trusted identity and request-reader ports. It
  requires business/hotel binding, active staff-directory membership and a
  complete committed audit chain; checks request version and Workpeg fingerprint
  for staleness; and returns an unpersisted plan (`persisted=False`). It does
  not implement either trusted port or Workpeg authorization.
- `domain/workpeg_writer.py::NativeRequestWriter` is the existing canonical
  request/audit writer boundary. It is disabled by default and requires a
  verified context, canonical plan, all-writer serialization lease, Workpeg
  table port, and verified table/write scope. It sequences pending audit,
  request update and committed audit with independent full reads and sanitized
  uncertainty results. No production route constructs it.
- `domain/workpeg_staff_identity.py` and `domain/workpeg_function_tables.py`
  define further server-side seams, but no verified-session resolver, current
  membership source, Roomay hotel mapping, staff roster, or production Function
  invocation binding is wired to Reception.

These contracts can be reused without changing their ownership or creating a
second writer. No staff operation can safely be integrated into the UI today.
The installed Workpeg 0.152.0 UI supports documented authenticated table helpers,
including `update_row`; those helpers alone do not provide Roomay department
authorization, all-writer serialization, audit reconciliation, or proof of
persisted readback. The current table permission is owner-only `700`.

## Blockers and enabling evidence

Linear state was checked on 14 Nov 2026. WOR-34 is In Progress and assigned to
Aliameen. WOR-28 and WOR-29 are In Progress under Umar; WOR-14 is In Progress
under another teammate; WOR-65 remains Backlog under Yusuf. Their branches and
contracts remain teammate-owned.

Before enabling a staff action, require all of the following evidence:

1. **Staff identity and scope:** a Workpeg-supported trusted boundary resolves
   the active signed-in staff subject, current business membership/revocation,
   Roomay hotel mapping, department and server-maintained Roomay roles. No
   browser claim or Workpeg owner/admin role may stand in for the Roomay roster.
2. **WOR-28 permissions:** authorized separate test accounts prove expected
   allow and deny behavior for table and row reads/writes, including a regular
   member, wrong department, wrong business and guest. The existing owner-only
   `700` policy stays unchanged until an owner-reviewed least-privilege policy
   and those results are documented. Table-list `200 []` alone is not enough.
3. **WOR-29 canonical data:** reviewed request/audit schemas and complete
   business-scoped pagination are verified; native row ids, row fingerprints,
   request ids and audit links are read back correctly; duplicate rows and
   malformed or partial data fail closed. No competing persistence adapter is
   introduced.
4. **WOR-14 lifecycle:** its assigned owner supplies the accepted assignment,
   acknowledgement, in-progress and resolution contract, including staff
   department rules, actor/time audit fields, denied transitions and refresh
   behavior. The existing domain transition rules remain canonical.
5. **WOR-65/shared writer:** the approved single-writer integration and any
   guest-to-staff bridge are coordinated with its owner. Reception must use the
   canonical Workpeg request and audit ids; the dormant PostgreSQL prototype is
   not a fallback.
6. **Concurrency and persistence:** prove a transaction/CAS or serialization
   guard that covers every writer, plus idempotent replay and pending-audit →
   request → committed-audit reconciliation. Show timeout/partial-write recovery
   and an independent Workpeg readback of both the target status and committed
   audit before reporting success.
7. **Negative acceptance:** demonstrate stale snapshot, duplicate operation,
   invalid transition, unauthorized staff, cross-business/department, unavailable
   Workpeg and malformed audit outcomes. They must return safe errors, not
   optimistic status changes or automatic duplicate retries.

No hosted Workpeg mutations, permission changes, Function publication or
deployment were made for this UI preparation. Offline tests prove only the
contract behavior, not hosted role grants or persistence.

## SDK references

The pinned local package is Workpeg 0.152.0. The official
[Tables & Rows documentation](https://developers.workpeg.com/docs/latest/tables/)
documents business-scoped, session-protected Peg UI helpers and states that
row `PATCH` replaces the entire `data` object. It describes row fingerprints as
change markers, not a conditional update primitive. The
[Widgets documentation](https://developers.workpeg.com/docs/latest/widgets/)
is the component API reference for the native controls used by this view.
