# WOR-34 receptionist application

> The historical namespace rejection described in this document was later
> resolved in the Roomay AI development business. The owner reports verified
> persistence for the existing `room_types` table; the remaining table schemas
> and staff permissions are separate open gates. This route remains read-only.

WOR-34 replaces the release demo with an authenticated, business-scoped,
read-only receptionist route:

```text
/b/<business_id>/reception
```

The route uses the Workpeg 0.149.1 `Authenticated` widget, the router's
`route.business_id`, and the documented `workpeg.get_tables()` and
`workpeg.get_rows()` helpers. It loads all pages for the exact nine-table WOR-29
contract. It does not call create, add, update, or delete helpers.

## What is implemented and verified offline

- The URL business ID must be a canonical UUID. Workpeg scopes table calls to
  that active business, and every returned row must repeat that same
  `business_id` value.
- Tables must match exact namespace, name, owner-only permission (`700`),
  columns, required flags, and supported field types before any row is shown.
- The complete room types, rooms, guests, reservations, stays, occupants,
  maintenance blocks, service requests, and request audit snapshot is paged and
  validated before the UI enters `loaded` state.
- The dashboard shows physical active stays separately from reservations. Its
  check-in readiness mirror is regression-pinned to `domain.hotel.room_eligibility`.
- The compiled validator mirrors the canonical stay/occupant chronology rules:
  checkout status and timestamp must agree, checkout cannot precede check-in,
  and registered occupants must remain within the physical stay interval.
- Scheduled departures today and overdue active stays are shown separately.
  An overdue stay remains physically in house until checkout is recorded.
- Invalid operational-date input retains the last valid date and shows a
  validation error, so existing metrics are never relabelled with an invalid date.
- Loading, empty inventory, authentication required, access denied, connection
  unavailable, and loaded states are explicit. Failed or partial snapshots show
  no hotel records.
- The browser-local operational date comes from the SDK `dates.today()`
  capability and remains editable. The UI explicitly says it is browser-local
  because the current model does not persist a hotel timezone.
- No mutation controls are enabled. A locally eligible room is not represented
  as a committed booking or authorization to check in.
- A real Chrome render against the local non-`--fake-cloud` server reached the
  route and displayed the SDK authentication gate: `Couldn't verify your
  session. Please retry.` This is browser-render evidence for the unauthenticated
  state only, not a live Workpeg persistence result.
- `/demo/reception`, `/b/<business_id>/dev-smoke`, and
  `/b/<business_id>/hotel-data` are absent from the release router. The
  diagnostic modules remain isolated for offline tests, coordinating with
  WOR-33 without deleting its evidence.

## Authorization boundary

The current reviewed table contract is permission `700`, so this release is an
owner-only read surface. The installed SDK documents authentication gating and
business-scoped table calls, but no verified `/users/me` role/membership payload
contract was found that would justify inventing receptionist department claims
in the browser. A `403` therefore fails closed as **Access denied**. Supporting
non-owner reception staff requires a reviewed table-permission or individual
grant design plus an authenticated live multi-role test; the UI does not weaken
the table contract to simulate that support.

## Room-change history dependency

A service request retains its persisted `room_id` as the room context where the
request originated. The receptionist validator therefore does not reject a
historical request merely because the linked stay now points at a different
room after a transfer. Stay/guest membership and both room identities must still
be valid.

The current nine-table contract has no canonical room-move audit record that can
prove the transfer sequence, actor, authorization, old room, new room, and
effective timestamp. That production audit contract belongs to WOR-12 and must
be designed and persisted before Roomay claims a complete room-change history.
WOR-34 preserves the original request context but does not invent that missing
audit trail or enable room-change writes.

## Still requires authorized live validation

The current Tables response is still:

```text
HTTP 400
Unknown peg namespace 'roomay'
```

No live Workpeg call, `--fake-cloud`, token, publication, installation, or data
write was performed for this change. After WOR-28 resolves the namespace:

1. Confirm the reviewed Peg release is installed in the exact Roomay
   development business; approval alone is not installation.
2. Sign in as an authorized owner and open the receptionist route for that
   business UUID.
3. With synthetic development-business records only, verify all nine tables,
   pagination, reload persistence, empty inventory, a denied second role, and a
   network interruption. Redact business identifiers and guest data in evidence.
4. Verify the business timezone contract before treating browser-local "Today"
   as the hotel's authoritative operating date.
5. Keep booking, assignment, check-in, and service-request writes disabled until
   a trusted concurrency-safe writer and WOR-14 authorization enforcement are
   implemented and tested.

WOR-34 must remain In Progress until the authenticated live acceptance criteria
pass. A successful offline build or mocked browser test is not proof of hosted
Workpeg persistence.
