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
* `resolve_tables_for_write()` accepts either (a) the prior explicit,
  trusted registered Peg identifier and exact type/value comparison for each
  returned `table.peg`, or (b) an in-process attestation issued only by
  `WorkpegFunctionTables` after authenticated reads of both canonical
  namespaces. The second path uses Workpeg's documented Function-token scope
  instead of requiring a separate local slug-to-internal-ID lookup.
* Peg UI `workpeg.get_tables()` automatically sends `Peg-Namespace`. That
  header is a client-supplied list filter; this change does **not** treat it
  as ownership proof. The alternative is specifically the server-side
  Function invocation token: current Workpeg docs say it is minted for one
  call, names Peg namespace/business/person, expires after 15 minutes, and
  the Tables API restricts it to that installed Peg's tables and the invoking
  person's permissions. The adapter sends it only in HTTPS `Authorization:
  Bearer` requests to the fixed Tables API host; it never uses `WORKPEG_PK`.
* The attestation is limited to the exact two fetched table lists, expected
  business, `roomay` namespace and actor resolved by the trusted caller. It
  supplements the unchanged full schema, namespace, permission, native UUID
  and row checks. A browser header, local config string, untrusted context
  dict, caller-constructed proof, missing schema metadata or API denial
  cannot issue an attestation. Explicit typed UUID validation remains
  available.
* This is an offline adapter implementation, not evidence that a Function has
  been published, installed, invoked, or has read the hosted tables. The
  current `function/app/main.py` remains inactive; the writer remains
  disabled and unwired. The observed internal UUID is therefore no longer a
  required config input **for a future Function-token path**; explicit-ID
  callers still need an exact trusted ID.

## Coordinator gates and operation sequence

The future caller must provide all of these from trusted server-side sources:

1. Authenticated active Workpeg business membership and exact business binding.
2. A verified actor mapping and authorization for this exact request operation.
3. Either an exact trusted registered Peg ID matching all nine metadata
   values, or a fresh Workpeg Function-token-scoped inventory attestation for
   the expected business/person/Peg and all nine canonical schemas.
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
business-member or guest access. A Function token does not elevate the
invoking person: Workpeg says the Tables API acts as that person and enforces
their table permissions. `StaffActionGateway` identity, actor-to-department
roster, and the writer's trusted context/serialization ports remain
unimplemented integrations, not guarantees established by this adapter. The
coordinator is not connected to `WORKPEG_PK` or an unverified external Tables
credential.

## WOR-28 / WOR-29 acceptance status

### WOR-28 — PARTIAL / HOSTED CHECKS REMAIN

Previously reported owner UI read success and Member UI fail-closed behavior
remain useful evidence for those two UI sessions. They do not establish direct
row denial, server-side actor identity, or a backend write path. The owner has
now reported current metadata for all nine tables with expected
namespace/schema/permission and the same UUID-formatted `peg` value; this
change does not independently query or alter hosted records. Official Function
token scoping provides a documented alternative for a future Function to
establish Peg ownership through successful server-authorized API reads. That
adapter is tested only with mocks. Real Function-token reads, actor/business
binding, and direct denial outcomes remain NOT VERIFIED.

### WOR-29 — OFFLINE FOUNDATION IMPLEMENTED / HOSTED ACCEPTANCE BLOCKED

The canonical nine schemas, complete pagination, snapshot validation,
request/audit reconciliation, and full-row update rules are reused. The new
ownership gate and disabled writer coordinator are covered by mocks. Hosted
write permission, actor authorization, a global serialization guarantee, and
post-write reload evidence are not established. Explicit UUID comparison and
Function-token-scoped ownership are both represented offline. Neither
establishes hosted write permissions or serialization. The previously reported
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
2. For an explicit-ID adapter, require exact schema, `700` permission, and
   exact typed `peg` agreement. For the Function-token adapter, invoke only
   inside an actual Workpeg Function call; require its platform-minted
   `context.token` and `context.business`, then GET both namespaces with that
   bearer token and no user-selected `Peg-Namespace` header. Require exact
   canonical schemas and fail closed on 401/403/404, empty or incomplete
   inventory, or mismatch. Do not run this path until a Function is separately
   reviewed, installed, and authorized.
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

## Remaining Workpeg question before any hosted write

Current official docs establish a server-side Function token bound to its
invoking person, business and Peg, and say the Tables API enforces that person's
table permissions. They do not document transactions or conditional
compare-and-swap for row updates. Please confirm whether Workpeg provides a
supported transaction, conditional update, uniqueness/idempotency constraint,
or platform-wide serialization primitive that coordinates every writer for
one request and its audit event. If none exists, identify the supported way to
ensure a single writer across Function instances and retries. Until answered
and verified, the writer must stay disabled.

## Resumption guidance for Aliameen

* Read-only hotel projections may continue using the owner-authenticated UI
  adapter and fail closed for Member access.
* Offline domain, writer-port, and authorization test work may continue using
  this coordinator without enabling it.
* Guest request persistence, staff state transitions, department inbox actions,
  check-in/checkout writes, and staff role grants must remain blocked until the
  identity, permission/privacy, and serialization guarantees above are
  verified and a separate live operation is approved.
