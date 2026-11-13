# WOR-28 / WOR-29 Native Persistence Foundation

## Scope and status

This change adds offline-tested contracts only. It makes no Workpeg calls and
does not instantiate the writer from a route, UI, Function, hook, or release
entry point. `NativeRequestWriter` is disabled by default. Its successful tests
use a deterministic in-memory mock of the documented table helper surface;
they do not demonstrate hosted permission, authorization, atomicity, or
persistence.

The existing `domain/service_requests.py` lifecycle remains canonical. The
existing `StaffActionGateway` remains the staff authorization/plan boundary.
The coordinator accepts a trusted plan factory so a future supported server
adapter can reuse those contracts; it does not trust a browser-supplied role,
business, actor, plan, or operation result.

## Ownership validation

Read compatibility and write readiness are separate:

* `resolve_tables()` continues validating the nine canonical schemas and
  `700` permissions without requiring a `peg` value. This preserves existing
  authenticated read-only behavior when ownership is unavailable.
* `resolve_tables_for_write()` additionally requires every canonical table to
  return the exact registered Peg identifier, including its native type. It
  rejects missing, null, malformed, different, and type-coerced ownership.
  The Peg identifier must be provided by trusted registration/configuration;
  namespace `roomay` alone is not proof of ownership.

There is a Workpeg documentation discrepancy to resolve before hosted writer
readiness. The [official Tables reference](https://developers.workpeg.com/docs/latest/tables/)
describes table `peg` as `number | null` and says the `Peg-Namespace` header
scopes table listing to the calling Peg. Roomay's earlier owner-observed
development metadata reported the approved Peg UUID as a string. The code
accepts either a canonical UUID string or positive integer as trusted config,
but requires the returned table value to match the configured value exactly;
it never converts a string to a number or vice versa. No live metadata was
queried for this PR.

## Coordinator gates and operation sequence

The future caller must provide all of these from trusted server-side sources:

1. Authenticated active Workpeg business membership and exact business binding.
2. A verified actor mapping and authorization for this exact request operation.
3. A verified registered Peg identity and exact ownership for all nine schemas.
4. Verified write permission for both `Roomay Service Requests` and
   `Roomay Service Request Audit` for that actor.
5. A serialization lease that is active, matches the business/request, covers
   every writer for that request, and also serializes the business idempotency
   namespace for request creation.
6. A canonical plan produced from current, complete Workpeg data through the
   existing domain gateway.

If any gate is absent, the operation is refused before mutation. The currently
approved `700` permission is owner-only; it does not authorize department
staff or prove that an owner is acting for a guest. No staff/guest writer is
currently enabled.

When all gates exist, the tested sequence is:

1. Acquire the verified serialization lease.
2. Read and validate both table namespaces, all nine schemas/owners, and every
   row page. Validate business scope, hotel snapshot, request relationships,
   audit history, native row IDs and fingerprints.
3. Ask the existing plan factory to authorize and prepare the exact canonical
   request transition. Check business/hotel/actor scope, version, stale
   fingerprint through the existing gateway, duplicate idempotency key, and
   operation ID collisions.
4. Append the exact audit event with `commit_state=pending`.
5. Read all rows again. Apply the request as a new row or full-data PATCH only
   if reconciliation says that is the single safe next step. Preserve every
   existing `data` field on PATCH.
6. Read all rows again. Mark the audit row committed only when the request
   exactly matches the target state.
7. Independently read all canonical rows again. Return `persisted=true` only
   when the request and matching committed audit satisfy
   `domain/service_requests.py::reconcile_write`.

The narrow snapshot option that permits one pending audit row without its
request exists only for the first step of a new request. It is constrained to
the exact request ID, pending state, and sequence 1. General snapshot
validation still rejects orphan events.

Any timeout or malformed response after a write stops further writes. The
coordinator performs a read-only reconciliation attempt; it does not retry the
write. If it cannot establish a complete committed pair, it returns an
uncertain/manual-review result with `persisted=false`. A confirmed pair after
an ambiguous response is reported only after fresh canonical readback.

## Workpeg guarantees still missing

The official SDK 0.152.0 UI helpers expose `get_tables`, `get_rows`,
`add_row`, and `update_row`; the official reference says PATCH replaces the
whole `data` object, so callers must preserve all columns. It describes
fingerprints as opaque change markers, not conditional writes. No transaction
or compare-and-swap mechanism for request plus audit was found. The coordinator
therefore refuses to operate without a verified all-writers serialization
lease. A Python process-local lock would not meet that contract.

Table permission `700` grants the table owner read/write/share and grants no
business-member or guest access. A trusted server-side route that can use an
owner-held session without exposing raw private rows to a browser is not
implemented here. Current `StaffActionGateway` identity and readers are
injected seams, not Workpeg authentication integrations. The coordinator is
not connected to `WORKPEG_PK` or an unverified external Tables credential.

## WOR-28 / WOR-29 acceptance status

### WOR-28 — PARTIAL / HOSTED CHECKS REMAIN

Previously reported owner UI read success and Member UI fail-closed behavior
remain useful evidence for those two UI sessions. They do not establish direct
row denial, server-side actor identity, Peg ownership for every current table,
or a backend write path. This PR validates ownership offline and deliberately
does not repeat live reads. Direct table/row denial remains NOT VERIFIED unless
Workpeg provides an already-authorized supported path to test it.

### WOR-29 — OFFLINE FOUNDATION IMPLEMENTED / HOSTED ACCEPTANCE BLOCKED

The canonical nine schemas, complete pagination, snapshot validation,
request/audit reconciliation, and full-row update rules are reused. The new
ownership gate and disabled writer coordinator are covered by mocks. Hosted
write permission, actor authorization, a global serialization guarantee, and
post-write reload evidence are not established. The previously reported
pending event is not read, retried, or modified by this change; its current
state remains unverified here.

## One owner-controlled live acceptance procedure — NOT AUTHORIZED BY THIS PR

Do not run this procedure until the owner separately approves the exact
preview and Workpeg has confirmed the permissions and serialization gates.
Do not reuse or change the existing Room 205 request/audit rows, especially
the previously observed pending event.

1. In the installed approved Roomay Peg, sign in as the owner in the isolated
   Roomay AI development business. Record the business ID and current Peg
   registration through the dashboard. Do not copy credentials into logs.
2. From the supported authenticated Reception read path, refresh both table
   namespaces. Require exactly nine canonical tables, all exact schema and
   `700` permission, and exact typed `peg` agreement with the approved Peg.
   If `peg` is absent or the observed UUID/string disagrees with the documented
   type, stop and request Workpeg clarification.
3. Read every row page from all nine tables. Validate the complete hotel
   snapshot and current request/audit history. Do not infer that an unreadable
   table is empty. Preserve all existing rows and the pending event.
4. Separately prove a trusted, authorized guest action for one existing
   fictional active stay and prove write permission to both request and audit
   tables. Table-owner access alone is not guest authorization. Prove a
   serialization mechanism covers all request writers and duplicate
   idempotency submissions. If any proof is unavailable, stop without writes.
5. Prepare one new request using the existing active stay's verified
   `hotel_id`, `stay_id`, `room_id`, and `guest_id` (never room-number input as
   identity):

   * Category: `extra_towels`
   * Department: `housekeeping` (derived by canonical routing)
   * Description: `Please bring two extra towels (WOR-28 acceptance test).`
   * Urgency: `normal`; origin: `guest`; sensitive: `false`
   * Status: `received`; version: `1`
   * New deterministic request UUID, idempotency key, event UUID, operation
     UUID and operation signature are generated in the owner-reviewed preview.
   * Request fields also include timestamps/deadlines from the trusted clock,
     `last_event_id` and `last_operation_signature` matching the event.
   * Audit event fields: `event_type=created`, sequence `1`,
     `from_status=null`, `to_status=received`, verified guest actor, same hotel
     and request IDs, matching operation signature, and initially
     `commit_state=pending`.

   The exact generated IDs, timestamps, payloads, and fingerprints must be
   shown to and approved by the owner immediately before any write. This
   document intentionally does not invent the hosted guest/stay UUIDs.
6. Under the approved writer only: add the pending audit row and read it back;
   add the request row and read it back; update the audit row to committed
   using full `data` preservation; then independently re-read both tables and
   validate the complete snapshot, audit/request signature, native Workpeg
   row IDs and changed fingerprints.
7. Reload the authorized UI and verify the exact request plus committed audit.
   A row appearing in the UI is not sufficient without matching committed
   audit verification.
8. If an operation times out, gets denied, returns malformed data, or cannot
   be read back, stop. Do not retry, delete, roll back, mark committed, or
   claim success. Perform read-only reconciliation and leave ambiguous state
   for owner review.

## Single Workpeg clarification to unblock the hosted path

Please confirm the authoritative type/source of `tables[].peg` for an
installed Peg and whether Workpeg provides a supported server-side execution
and authorization mechanism that can both (a) bind the authenticated caller to
the active business and enforce per-actor/department permissions without
exposing private table rows, and (b) serialize all writes for the same request
and idempotency key or conditionally/atomically commit the request plus audit
rows. If the answer is no, specify the supported mechanism and guarantees that
replace these requirements.

## Resumption guidance for Aliameen

* Read-only hotel projections may continue using the owner-authenticated UI
  adapter and fail closed for Member access.
* Offline domain, writer-port, and authorization test work may continue using
  this coordinator without enabling it.
* Guest request persistence, staff state transitions, department inbox actions,
  check-in/checkout writes, and staff role grants must remain blocked until the
  identity, permission/privacy, and serialization guarantees above are
  verified and a separate live operation is approved.
