# Roomay staff access and guest privacy model (WOR-51)

This is a proposed least-privilege product policy and an offline test contract.
It does not log a user in, authenticate a Workpeg session, assign Workpeg roles,
or change live table permissions. The Workpeg permissions needed to enforce this
model have not been verified. Keep protected writes and private record views
disabled until the trusted Workpeg boundary proves them.

## Simple rule

People get only the records and actions they need for their job. A receptionist
handles arrivals and guest identity. Housekeeping sees room-cleaning work. A
maintenance worker sees repair work. A guest sees only their own limited stay
and request information after Roomay can bind them to an active registered
occupant. A hotel business boundary applies to every record. Missing or
unverified identity, membership, business binding, or row ownership means
access is refused.

In code, `domain/access_control.py` checks a proposed `AccessContext`, business
and hotel identity, resource, action, department, guest scope, and sensitivity. These
context values are claims that a future trusted adapter must establish from
Workpeg and a server-maintained staff directory. A browser-supplied role,
business ID, guest ID, or `verified=True` flag is not proof and must never be
passed directly as authority. `domain/hotel.py::validate_snapshot` remains the
canonical check for room, guest, reservation, stay, and occupant relationships.
The existing `domain/service_requests.py::request_view` remains the canonical
service-request lifecycle authorization rule.

## Proposed permission matrix

`Read` means read only the fields needed for the stated work. `Operate` means
only the listed job actions; it does not grant table administration. `Own` is
restricted to a verified guest's own identity and active registered stay.
`—` means denied by default.

| Information / operation | Owner/operator | Manager | Receptionist | Housekeeping | Maintenance | Guest | Nonmember |
|---|---|---|---|---|---|---|---|
| Room directory (number/type) | Read, manage | Read, manage | Read | Read minimal | Read minimal | — | — |
| Availability and reservations | Read, manage | Read, manage | Read; create requests; confirm/cancel only through protected gates | — | — | — pending a separately verified guest reservation view | — |
| Check-in records and registered occupants | Read, manage | Read, manage | Read; check-in/out only through protected gates | — | — | Own stay summary only | — |
| Guest personal data | Read, manage | Read, manage | Read for reception duties | — | — | Own minimal profile | — |
| Housekeeping readiness | Read, manage | Read, manage | Read | Read, update cleaning/inspection status | — | — | — |
| Maintenance blocks | Read, manage, release | Read, manage, release | Read | — | Read, create/update/release assigned operational blocks | — | — |
| Maintenance requests | Read, manage | Read, manage | Read/create and route | — | Read/update maintenance work | Submit own help request only | — |
| Service requests | Read/manage, including sensitive | Read/manage, including sensitive | Read, create, assign, triage, cancel; sensitive only with verified incident authority | Read/update housekeeping requests only | Read/update maintenance requests only | Read/create own requests; cannot self-resolve | — |
| Audit trails | Read only | Read only | — | — | — | — | — |
| Management information | Read | Read | — | — | — | — | — |
| Permission configuration / table administration | Owner-managed Workpeg controls; separate approval | — | — | — | — | — | — |

The offline module additionally recognizes a server-verified `incident_manager`
privilege for sensitive service-request visibility. Department staff access is
bound to the request's routed department; departmental request projections omit
guest, stay, hotel, idempotency, and audit-linkage identifiers. Guest request
projections omit room and staff identity. The actual UI and Workpeg rows do not
yet enforce these projections.

## Privacy and data handling requirements

- Resolve the actor from the authenticated Workpeg session, then look up active
  hotel membership and role in a trusted staff directory. Never infer authority
  from the URL, a form value, AI output, a request body, caller ID, or QR code.
- Resolve one active Workpeg business and compare it with the requested business
  and every row's required `business_id`. Also bind each hotel's records to the
  trusted active `hotel_id`, even when multiple hotels share a business. A
  mismatch or missing identity rejects the complete response; never fall back
  to another hotel or data store.
- Validate the complete hotel snapshot before using references. Reject missing,
  malformed, duplicate, or cross-linked rooms, guests, reservations, stays,
  occupants, and blocks. Reuse canonical `validate_snapshot` rather than
  creating a second hotel relationship validator.
- Show room-cleaning staff room identifiers and cleaning state without guest
  names, reservation dates, occupant lists, or contact information. Maintenance
  receives only the room and repair context necessary to do the assigned work.
- Limit guest access to a verified matching guest identity and active registered
  stay. Reservation visibility is currently denied to guest contexts; any future
  guest booking view needs a separate verified ownership contract.
- Keep request descriptions and sensitive incident details private. Department
  staff receive their own department's operational request projection. Sensitive
  incidents require a manager or separately verified incident manager.
- Audit access to guest identity, reservation/check-in changes, room moves,
  maintenance blocks, sensitive escalations, and permission changes. Audit rows
  are read-only to managers and owner/operators; ordinary staff and guests do
  not receive audit history.
- Error surfaces use fixed safe messages. Never render a raw exception, row,
  server response, token, internal identifier, or guest description as an error.
  Keep detailed diagnostics in an access-controlled server log only.
- Establish approved retention, redaction, access review, incident response,
  and staff offboarding processes before storing real guest records.

## Approved and prohibited actions by role

### Owner/operator

May inspect and operate hotel records, review management information and audit
history, and sponsor Workpeg staff/permission configuration. A role label alone
does not grant configuration access; Workpeg's own authorized owner controls and
reviewed changes remain required. Do not grant AI direct write access.

### Manager

May supervise hotel operations, review sensitive requests and audit history,
and approve sensitive escalation. Reservation, check-in, room-block, and guest
record changes still require the protected write sequence and audit evidence.

### Receptionist

May view arrivals, departures, room readiness, reservations, registered
occupants, and guest identity needed for front-desk duties. May prepare requests,
route service issues, and perform confirmation/check-in only after the separate
server-side authorization and concurrency gates pass. Cannot alter role
configuration or read audit/management data by default.

### Housekeeping staff

May view room number/type and housekeeping tasks, then update the cleaning or
inspection state for assigned work. Cannot read guest identity, reservation or
check-in records, registered occupants, maintenance details, or audit history.

### Maintenance staff

May view minimal room identifiers and maintenance requests/blocks needed for
repairs. Cannot read guest identity, reservations, active occupant lists, guest
service details outside maintenance, or audit history. A block must not be used
to overwrite a reservation or hide an occupied room.

### Guest

May submit a request and see a minimal view of their own request or active stay
only after a verified identity-to-occupant binding. Cannot see another guest,
staff directory, hotel-wide availability, room assignment, internal request
notes, or audit details; cannot confirm, check in, resolve, or assign a request.

### Unauthorized or nonmember user

May access no business records. Return a safe denial and do not reveal whether a
guest, reservation, room, request, or table exists.

## High-risk scenarios and fail-closed response

| Scenario | Required result |
|---|---|
| Browser posts `role=manager` or a different business UUID | Ignore client claim; rebuild context from Workpeg session; deny if the server cannot verify membership and business binding. |
| Guest asks for another guest, reservation, or request | Deny without confirming whether the target record exists. |
| Housekeeping opens a maintenance or reservation record | Deny by department/resource policy. |
| Maintenance opens a housekeeping request | Deny by department policy. |
| A row's `business_id` differs from the authenticated business | Hide the complete snapshot and return a fixed safe error. |
| Room, guest, reservation, stay, or occupant reference is malformed/missing | Reject the snapshot using the canonical hotel validator; do not render partial data. |
| Workpeg returns 401/403, timeout, missing table, malformed response, or unknown identity | Deny/mark unavailable; do not fallback to fixtures, another business, or broader permissions. |
| Sensitive request is read by ordinary reception or department staff | Deny; allow only manager or separately verified incident-manager authority. |
| Error message contains a guest name, description, or server payload | Replace it with a fixed public message; never echo raw exception text. |
| AI proposes an action or a save hook is bypassed | Treat AI as a suggestion only; require the same trusted authorization and write gates as staff. |

## Current Workpeg limits and what is not verified

- Hotel integration tables currently specify restrictive owner-only permission
  `700`. That is not proof that department-specific Workpeg access works; it may
  deny the receptionist and every department until an owner configures and
  verifies the intended grants.
- WOR-28 has not verified authenticated table CRUD/reload and permission
  behavior in the development business. Its namespace/install investigation is
  a prerequisite. Approval or a local build is not installation or access
  evidence.
- The Workpeg adapter validates table schema, row identity, business binding,
  and hotel relationships before rendering a read-only snapshot. It does not
  authenticate staff roles or filter the receptionist's full role-specific
  record view. Existing `ui/hotel_data.py` remains a receptionist implementation
  and was not changed by this issue.
- `domain/access_control.py` accepts typed offline claims and tests policy
  outcomes. Python values, boolean flags, a `department`, or a role string are
  forgeable outside a trusted adapter. These functions are not a Workpeg ACL,
  server boundary, or authorization token.
- Current Workpeg integration documentation reports no verified conditional
  update, transaction, uniqueness, or compare-and-swap helper. Access checks do
  not solve concurrent reservation or multi-row stay writes.
- Department filtering and safe projections are offline rules only. Workpeg
  table/row permissions, business membership, staff directory provenance,
  assigned-row filtering, audit visibility, and denial behavior are unverified.
- No live API calls, permission changes, table provisioning, real guest data, or
  hosted verification were performed for WOR-51.

## Owner-only live verification checklist

Run only after WOR-28 is resolved, in the isolated Roomay development business,
with synthetic records and an authorized owner. Record redacted results; never
copy tokens, guest details, or private row payloads into a PR.

1. Verify the Roomay Peg is installed in the exact development business and the
   authenticated Workpeg session identifies the expected business.
2. Create a least-privilege staff matrix for owner/operator, manager,
   receptionist, housekeeping, maintenance, and guest; verify each role on the
   server and reject inactive staff, nonmembers, stale sessions, and changed
   business routes.
3. Confirm restrictive table permissions and row-level grants. Test same-role
   allowed reads and writes, every denied role/resource pair, cross-business
   access, cross-guest access, and cross-department request access.
4. Verify minimal projections: housekeeping cannot obtain guest identity or
   reservation data; maintenance cannot obtain occupant/contact data; guests
   can obtain only their own active stay and request fields.
5. Verify error handling for 401, 403, missing tables, malformed references,
   timeout, and partial reads. Ensure no private data appears in UI errors,
   logs, browser bundles, or AI context.
6. Verify audit attribution and access to sensitive requests, reservation and
   check-in changes, maintenance blocks, and permission changes.
7. Repeat after refresh and in a second business; prove that grants and
   business isolation survive reload and cannot be bypassed through direct row
   helper calls or declarative AI writes.
8. Do not enable protected actions until this review, the server-side
   authorization path, and separate concurrency/write gates have passed.

## WOR-22 / WOR-28 dependencies

WOR-51 prepares the role policy and local negative tests for parent WOR-22. It
does not close WOR-22. WOR-28 must first verify the installed Peg, authenticated
business identity, CRUD behavior, and least-privilege Workpeg permission model.
After that, the trusted adapter must connect Workpeg identities to this offline
policy, enforce row/field projections server-side, and pass owner-run hosted
denial and audit tests before any protected UI action is enabled.
