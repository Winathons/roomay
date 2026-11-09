# WOR-49 — authorized staff request operations

## Scope and status

This change adds an offline staff-action adapter contract around the existing
`domain/service_requests.py` lifecycle. It supports only assignment,
acknowledgement, start-work, resolution and escalation. The department inbox
projection reuses `domain/access_control.py`; it is not a second inbox or a new
database. No production route was added, no Workpeg permission was changed and
no hosted write was performed.

The owner has verified a complete fictional request in the Reception Workspace.
That verifies owner-context reads for that UI and data. It does not prove that a
Housekeeping employee can read or transition the request.

## Trust boundary

`domain/staff_actions.py::StaffActionGateway` rejects browser-supplied actor,
role, business, hotel, department, membership or permission fields. It accepts
only the request ID, supported action, stable operation key, expected request
version/fingerprint and action-specific inputs. Before making a plan it calls
two injected ports:

1. An identity resolver that must verify the authenticated Workpeg session,
   active business membership, staff subject, hotel mapping, department, roles
   and active status from trusted platform data.
2. A request reader that must fetch the row and audit history from that same
   verified business and provide the native Workpeg row fingerprint.

These ports are interfaces only. They are not backed by a verified Workpeg
identity resolver, server service or staff directory in this repository. A
Python dataclass, UI route parameter, typed confirmation, client role, or mocked
resolver is not authentication. Therefore this module produces plans only;
every new plan says `persisted=False`.

## Supported operations

| Command | Domain transition | Authorization source |
|---|---|---|
| `assign` | received/reopened/escalated -> assigned | Reception or request administrator; active assignee must belong to routed department |
| `acknowledge` | assigned -> acknowledged | Assigned employee, same-department supervisor, or administrator |
| `start_work` | acknowledged -> in_progress | Assigned employee, same-department supervisor, or administrator |
| `resolve` | in_progress -> resolved | Assigned employee, same-department supervisor, or administrator |
| `escalate` | active state -> escalated | Existing domain transition policy; sensitive request requires manager/incident authority |

The canonical service-request module remains responsible for transition
validity, role checks, sensitive escalation, timestamp monotonicity and
idempotency signatures. Department inbox cards use the existing least-privilege
projection; department staff see only their routed department and do not receive
guest/stay/hotel/idempotency/audit-linkage fields. The guest status projection
continues to show only the guest's request fields and never staff/audit identity.

## Workpeg permission model verified in documentation and SDK 0.152.0

Workpeg's table permission is three Unix-style digits: owner, business staff,
and public, with `4=read`, `2=write`, `1=share`. Thus table permission `700`
grants the owner read/write/share and grants no general business-staff or public
permission. Workpeg also documents individual table and individual row grants;
only the table owner may create/change these grants. The documented routes are
`GET/POST /v1/businesses/{business_id}/tables/{table_uuid}/individual-permissions/`
and `GET/POST /v1/businesses/{business_id}/tables/{table_uuid}/rows/{row_id}/individual-row-permissions/`.
SDK 0.152.0's UI client exposes `get_protected(url)`,
`post_protected(url, data=None)`, `put_protected`, `patch_protected` and
`delete_protected`; the SDK uses authenticated protected requests. This PR does
not call them.

These permissions are for individual staff IDs, not Workpeg departments or
Roomay roles. A table-wide grant is not department scoping. A row-level grant is
per row and per person, so future rows would need new grants. Current service
request row payloads set both `inherit_business_permission` and
`inherit_individual_permissions` to `false`.

The service-request table stores guest, stay, hotel, room, idempotency and free
text fields in the same row. The audit table stores operation signatures,
actor identity and reasons. The documented permission model is table/row-level;
no column-level field masking is documented. Giving a Housekeeping staff member
row-read access therefore exposes that entire request row, even if Roomay's
Python projection would hide some fields. This is not currently acceptable as a
least-privilege guest privacy boundary. Keep the existing tables at owner-only
`700`; do not grant staff table or row access until Workpeg behavior and an
approved privacy design are verified.

Before staff operations can go live, the owner and Workpeg must approve and test
one of these options:

1. A supported server-side authenticated gateway that reads owner-protected
   records and returns only the existing role-scoped projections, while
   authorizing each action from verified staff identity and serializing writes;
   or
2. A reviewed schema/permission redesign that avoids exposing private request
   fields through row-level grants while still making department operations
   possible.

Do not treat a helper's `get_protected` session cookie, UI-level filtering, or
an owner-run individual-permission call as a staff authorization test. No
department-group permission or field-level permission behavior was found in the
documented model.

Official references: [Workpeg Tables and Rows](https://developers.workpeg.com/docs/latest/tables/)
and installed `workpeg==0.152.0` signatures in
`workpeg/ui/app.py` (`get_protected`, `post_protected`, `put_protected`,
`patch_protected`, `delete_protected`).

## Persistence and uncertain writes

The adapter checks the expected request version and native Workpeg fingerprint
against a fresh read before preparing an action. This catches stale browser
state, but Workpeg documents fingerprints as change markers and does not
document conditional row updates or compare-and-swap. A concurrent writer can
still change a row after the read. No online mutation is safe until a trusted
server serializes every writer per request (including other UIs/AI paths) or
Workpeg provides an equivalent atomic guard.

Once an authorized serialized writer exists, continue using
`domain/service_requests.py::reconcile_write` and full-row payload encoders:

1. Read the canonical request row and its complete paginated audit history.
2. Verify business, request identity, expected version and latest fingerprint.
3. Append the deterministic audit event as `pending`.
4. Read back event and request; apply the full request row only if its base
   contents still match.
5. Read back the exact target request, mark the event `committed`, then verify
   both rows again.
6. On timeout, partial write, duplicate event or mismatch, stop and reconcile;
   never blindly retry.

Workpeg PATCH replaces a supplied row `data` object as a whole, so the adapter
must preserve unrelated request fields. A committed audit event is evidence of
the row value only; it does not prove notification, acknowledgement or service
completion. Do not tell a guest or receptionist that staff were notified until a
separate verified delivery mechanism proves it.

## Consolidated offline acceptance

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe tests\run_staff_request_acceptance.py
```

This uses synthetic fixtures and mocked ports to exercise the existing request
state machine, trusted identity seam, role/department isolation, guest status
redaction, stale version/fingerprint refusal, duplicate delivery, audit
reconciliation, compiled receptionist/release tests and release-route gates.
It performs no Workpeg requests and is not evidence of hosted permissions.

## Owner acceptance after review

1. Keep existing Roomay AI tables and fictional rows unchanged.
2. Ask Workpeg to confirm staff/row individual permission semantics and whether
   a supported server-side identity/action gateway can use those permissions
   without exposing private row fields.
3. If an approved design is available, use separate test accounts for
   Reception, Housekeeping, Maintenance, another department and a nonmember.
   Prove allowed and denied table, row, guest-field and cross-business access.
4. Only after a separate approval, exercise one synthetic request per approved
   action. Verify request and audit values from a fresh authorized read, timeout
   reconciliation, duplicate delivery and guest status response. Do not use the
   owner's session as a substitute for department tests.
5. Keep the existing production Reception Workspace read-only until the
   permission/privacy design, server writer and concurrency guarantees pass.
