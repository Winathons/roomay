# WOR-14 service-request lifecycle

This document describes implemented, offline business logic and a **proposed**
Workpeg persistence contract. It is not evidence of hosted persistence. The live
Peg namespace/table resolution problem remains tracked in WOR-28, so no Workpeg
API was called and no table or function was published for WOR-14.

## Implemented domain contract

`domain/service_requests.py` owns the canonical request lifecycle. It validates a
complete hotel snapshot before accepting a request and requires the supplied stay
to be physically `checked_in`, the room to match that stay, and the requesting
guest to be a registered occupant who has not left. A reservation alone is not
enough.

Each request contains:

- UUID request, hotel, stay, room, guest and last-event identifiers;
- a hotel-scoped idempotency key;
- origin, category, routed department, description and urgency;
- status, optional assigned staff subject, SLA acknowledgement/due targets and
  lifecycle timestamps;
- sensitivity/triage flags and a monotonically increasing application version.

Every creation, transition and triage decision produces a deterministic operation
ID and an audit event containing actor, department, time, reason, prior/target
status and sequence. AI/system inputs are not accepted as authoritative actors.
The eventual adapter must construct staff actors from authenticated platform data;
caller-supplied role strings are only test inputs here.

### Status graph

The normal path is:

`Received → Assigned → Acknowledged → In Progress → Resolved`

Authorized alternatives are:

- active states may become `Cancelled` or `Escalated` with a reason;
- `Resolved` and `Cancelled` may become `Reopened` with a reason;
- `Reopened` and `Escalated` return through `Assigned` before work continues.

Reception or a request administrator assigns active staff in the routed
department. The assigned staff member, a supervisor in that department, or a
request administrator advances work. Guests cannot acknowledge, progress,
resolve, assign, cancel or escalate a request; an active registered guest may
reopen their own resolved request. Sensitive escalation and sensitive request
access require an incident manager or hotel manager.

Categories route to housekeeping, maintenance, food and beverage, or reception.
Unknown text is preserved as `category_detail`, stored as canonical `unknown`, and
routed to reception with `triage_required=true`. Reception must explicitly
classify it before another department can be assigned.

## Workpeg-compatible schema proposal

`domain/service_request_schema.py` proposes two tables in namespace
`roomay_requests_v1`:

1. `Roomay Service Requests` (`roomay-service-requests-v1`)
2. `Roomay Service Request Audit` (`roomay-service-request-audit-v1`)

Both default to permission `700`, and row payloads disable business and individual
permission inheritance. This is deliberately fail-closed: public/guest access and
broad business-wide write access would bypass department rules. A future trusted
gateway must grant documented individual row permissions only after resolving the
authenticated staff member and approved department membership. Sensitive audit
history should remain gateway-only.

The schemas use only documented `text`, `number`, `boolean`, `datetime`, `uuid`
and `mutable_select` columns with stable custom IDs. UUID references are
application associations, not Workpeg foreign keys. The request encoders always
send the full non-null `data` object because Workpeg `PATCH` replaces `data` as a
whole.

Official SDK evidence:

- [Tables and rows](https://developers.workpeg.com/docs/latest/tables/) documents
  business/Peg scoping, permissions, column types, row fingerprints, paginated
  reads, individual permissions, and `workpeg.get_tables`, `get_rows`, `add_row`
  and `update_row`.
- [Save hooks](https://developers.workpeg.com/docs/latest/hooks/) documents that
  pre-save hooks can reject ordinary writes, post-save hooks cannot roll a write
  back, and the declarative agent path currently does not run pre-save hooks.
- Installed SDK 0.149.1 source confirms the helper signatures in
  `ui/compiler/ast_parser.py` and the protected browser calls in
  `ui/runtime/workpeg-runtime.js`.

No transaction, unique constraint, foreign key, conditional fingerprint update,
or compare-and-swap primitive is documented. Fingerprints detect that a row
changed; they are not claimed as a write precondition.

## Persistence and retry protocol

The proposed adapter must serialize mutations per request and use the plan emitted
by the domain layer:

1. Read the complete request row and all audit rows for the deterministic
   operation ID. Duplicate operation rows are a hard reconciliation failure.
2. Append the audit event as `pending` if it does not exist.
3. Re-read and require the entire request to equal the plan's base request. Do not
   accept version equality alone.
4. Create/update the request using the complete target `data` object.
5. Re-read until the exact target is observed, then update the event to
   `committed` with its complete `data` object.
6. Re-read both rows before reporting success.

`reconcile_write()` returns only the next safe action: append the pending event,
apply the request, commit the event, complete, or a named manual-reconciliation
state. A timeout is an unknown outcome. The adapter must re-read; it must not
blindly resend a create or update. Conflicting base records, duplicate events,
changed event payloads and committed-event/request mismatches lock the operation
for human reconciliation.

Application idempotency still requires complete paginated reads because Workpeg
does not document a unique index or server-side row-value filter. This is not a
scalable or concurrency-safe hosted implementation until the gateway establishes
serialization and the platform behavior is verified.

## Integration requirements and limitations

Before claiming the Linear acceptance criteria:

1. Resolve WOR-28 namespace/table visibility and verify table create/read/update/
   reload in the isolated Roomay AI business.
2. Establish a trusted server-side gateway or another verified Workpeg mechanism
   that builds actors from authenticated identities, serializes per-request
   mutations and is the only writer. Do not expose `WORKPEG_PK` to a Peg UI.
3. Verify how business staff IDs and department membership are represented, then
   test row-level individual grants for correct department, wrong department,
   another business and guest/public access.
4. Provision the exact reviewed schemas once, verify schema/alias/permission on
   read-back, and refuse duplicate or unexpected tables.
5. Exercise creation, acknowledgement, resolution, reload persistence, duplicate
   delivery, timeout-after-write and partial journal failures with fictional data.
6. Add approved retention/redaction rules before any real guest description or
   audit history is stored.

A pre-save hook alone is not an acceptable authorization boundary today because
the official docs identify an agent-write path that bypasses it. No declarative AI
action should have direct write access to these tables. AI may suggest a category
or draft text, but the same authenticated domain command must authorize and record
the actual mutation.

## Verification

```powershell
python -m unittest discover -s tests -v
python -m compileall -q ui function domain tests
workpeg ui build ui/
git diff --check
```

Tests use only synthetic hotel data and in-memory records. They cover the normal
lifecycle, invalid transitions, idempotency conflicts, wrong department, expired
stay, cross-hotel/cross-guest access, sensitive escalation, reopening, schema
shape and failed-write reconciliation.
