# WOR-28 — Read-only Function-token acceptance

## Scope and result

The Function entrypoint now supports one narrowly shaped, read-only metadata
acceptance action. It reads table metadata in `roomay_hotel_v1` and
`roomay_requests_v1`, validates the nine existing canonical contracts, then
returns only sanitized flags. It does not read rows, inspect request/audit
history, or invoke a Workpeg write method. The production `workpeg.json`
remains `{"namespace":"roomay"}`; no action is registered, hook attached,
Function submitted, or hosted invocation made.

The action cannot accept actor, business, Peg, or token claims in its payload.
It accepts only `{}` and derives context exclusively from the Function
envelope. A successful read-only inventory response is:

```json
{
  "token_authorization": "accepted",
  "inventory": "complete",
  "peg_scope": "match",
  "business_scope": "match",
  "actor_presence": "unverified"
}
```

`token_authorization=accepted` means Workpeg accepted the platform-minted
Function token for the metadata reads. It does **not** establish a Roomay staff
identity or department role. `actor_presence` is reported separately and
remains `unverified` when Workpeg omits `context.staff.email`. The read-only
action never manufactures actor identity or an actor-bound write attestation.

Failure results contain the same five fields with `denied` or `unverified`,
`incomplete`, and where locally known `mismatch`. No email, business UUID,
table UUID, response body, row, token, or error string is returned.

## Workpeg invocation and authorization contract

The current official [Functions documentation](https://developers.workpeg.com/docs/latest/functions/)
defines `main(context, payload)` and warns that context fields differ by
invocation path. The Workpeg 0.162.0 SDK's manifest-action envelope contains
`action`, `table`, `phase`, `business`, and a per-invocation `token`; its action
envelope builder does not include `staff`. This handler therefore treats staff
identity as optional for this read-only diagnostic. If `staff.email` is
present in a real platform context, the result reports only its presence; if
absent, a successful scoped metadata read is reported with
`actor_presence=unverified`. This does not establish a Roomay role. Workpeg
authenticates the per-invocation token and enforces its Peg/business/person
permissions. `WORKPEG_PK` is only for the development listener and
registry/CDN submission; it is not a Tables credential and is never used by
this Function.

The [Manifest action contract](https://developers.workpeg.com/docs/latest/manifest/)
has a phase form: `via: {"table": "<alias>", "phase": "post_save_hook"}`.
On a supported installed/released action path, the phase is an invocation
label, not a request to save a row; the handler's fixed metadata GETs are
read-only. Do not attach an actual table save hook. A `pre_save_hook` return
may replace row data, and an actual post-save hook runs only after a row was
committed; neither is appropriate for this check. See the official [Save
hooks documentation](https://developers.workpeg.com/docs/latest/hooks/).

**Development-runner limitation:** the current official [dev-install
documentation](https://developers.workpeg.com/docs/latest/dev-install/)
explicitly lists phase actions and the agent envelope with a real token under
“Cannot be tested in dev.” The presence of `workpeg project serve` and
`workpeg function test --envelope action` in SDK 0.162.0 does not make this
specific phase action runnable in a dev install. The CLI fixture uses a
synthetic token and cannot establish platform authorization. Do not start a
listener or follow the hosted-action acceptance steps below expecting a real
phase-action context from the development runner. A real installed action
would require a separately approved supported Workpeg path; no such invocation
is authorized or verified by this PR.

### Separate development path: own row-save hook (not this action)

The same official dev-install guide documents a different local Function path:
with an eligible dev install and listener, a save made by the owner on that
owner's dev page can invoke a Function hook on the owner's computer. This is a
real row-save operation, not a phase action. Dev-page tables are isolated in a
Workpeg-generated `dv-<business-specific-uuid>` namespace, separate from the
released Peg tables and other businesses. A listener needs the owner's private
`WORKPEG_PK`; `--with docker` is the documented default and requires Docker.
The guide also says dev Function routes can answer 404 when the platform's
`DEV_FUNCTIONS_ENABLED` is off.

The current PR entrypoint is **not compatible with that row-save envelope**:
it requires `context.phase == "post_save_hook"` and an empty payload. The
official save-hook envelope instead contains platform-provided table, staff,
row, metadata, business and token context plus the saved row's `data` as the
payload; it does not carry the manifest action's `phase` field. A save-hook
acceptance would need a separately constrained test-only handler path. For a
`pre_save_hook`, the Function's return replaces the row data; a
`post_save_hook` runs after the row is already stored and its return is
ignored. The current `workpeg.json` declares no Function or action. No hook is
registered and no listener has been started.

Even after that test-only path is reviewed, a dev install proves access only
to its generated test tables. It must not be presented as proof that the
Function token can read the nine existing canonical tables in
`roomay_hotel_v1` and `roomay_requests_v1`, or that a manifest phase action
works. The current docs do not establish that the dev token can reach those
non-dev namespaces. Only a separately approved invocation may establish what
the platform actually authorizes.

### Proposed owner-approved mutation — not approved or executed

If the owner chooses the row-save route after the test-only handler is
reviewed, the single proposed operation is:

* **Business/Peg:** the owner selects the existing approved `roomay` Peg in
  the **Roomay AI development business**, privately confirms the active
  business, and confirms the Peg is installed for testing. The UUID of that
  business is not recorded here.
* **Table:** create exactly one table named `ROOMAY WOR-28 Function
  Acceptance` through that dev install. Let Workpeg assign the isolated
  `dv-<uuid>` scope; do not request either canonical Roomay table namespace.
  The exact generated UUID namespace is not available from this offline
  checkout. The owner must observe and confirm that the active dev page shows
  a `dv-…` namespace for Roomay AI before approving creation; stop if the
  scope cannot be verified. Read it back and verify it before saving a row.
* **Permission/schema:** owner-only permission `700`; six required text
  columns: `test_marker`, `token_authorization`, `inventory`, `peg_scope`,
  `business_scope`, and `actor_presence`. Stop if Workpeg cannot return that
  exact schema, scope and permission. No guest, stay, reservation, request or
  audit fields are included.
* **Hook and row:** the existing PR handler cannot run this test: it is
  action-only. Before any owner mutation, a reviewed test-only code path must
  accept only the documented row-save context for this exact table, reject
  other tables/payload shapes, use the invocation's `context.token` for one
  metadata GET of `context.table.uuid`, validate the six-column test
  contract, and return only the marker plus sanitized flags. The table hook
  must be `pre_save_hook` so validation runs before the test row is committed.
  Current Workpeg docs specify the hook reference form as
  `custom.<peg_namespace>:<version>`; for the approved Peg and version 1,
  the proposed value is `custom.roomay:1`. The owner must confirm that
  version 1 is included in the dev install before proceeding. The one row
  would contain only `test_marker=roomay-wor28-readonly-acceptance-v1` on
  input; the pre-save result would store the sanitized flags in the other
  five columns. It must not
  read or write any other row or table. This does not test the manifest phase
  action or validate the nine canonical schemas.
* **Cleanup:** no automatic retry, rollback or deletion. Retain the single
  clearly named test table and row until sanitized evidence is reviewed. The
  owner may separately approve deleting that table and row from the dev
  business afterward; do not delete anything automatically.

Before any of these changes, the owner must approve the table creation, the
one pre-save hook, and the one marker-row save together **after the
test-only handler has been implemented and reviewed**. Workpeg must confirm
the dev install is eligible and that the per-invocation token can read the
test table metadata. The local Workpeg
0.152.0 CLI cannot start this runner; the isolated 0.162.0 runner is
available, but no `WORKPEG_PK` is present in this Codex process. Docker is
installed but its engine was unavailable in this preflight; no listener has
been started. The owner must privately confirm
the Peg installation and current Roomay AI business in the dashboard. Stop if
any condition fails. No approval or live invocation has occurred for this
proposal.

The Function sends exactly two HTTPS `GET` requests using the platform token,
to the fixed Workpeg Tables API host and the platform-provided business UUID,
with the two canonical namespaces. It does not send a caller-supplied
`Peg-Namespace` header. Both reads must succeed before the handler reports the
token as accepted and validates canonical schemas with pure `resolve_tables()`.
It deliberately does not create a `FunctionPegScopeAttestation`: that proof
binds an actor and remains reserved for future writer readiness. No writer is
constructed or called.

Important result semantics:

* `peg_scope=match` means the token's namespace precheck is `roomay` **and**
  Workpeg accepted the token-scoped table-list reads. Decoding a JWT claim by
  itself is not authentication.
* `business_scope=match` means the authenticated GETs succeeded for the
  platform-provided `context.business`. It is **not** a compiled allowlist for
  the Roomay AI business. The owner must verify the Workpeg UI is currently
  scoped to **Roomay AI** before invoking. The official Function config
  reference does not document custom environment injection, and the exact
  Roomay AI business UUID is intentionally not embedded here.
* `actor_presence=verified` means the platform context included a non-empty
  staff email. It does not establish Roomay department membership or authorize
  Housekeeping/Member actions. When absent or malformed, it is `unverified`;
  the read-only result makes no actor claim.
* No Function-scope write attestation is created in this read-only path. No
  replay or write-readiness claim is made.

The Function Docker build context is `function/`, so repository-level
`domain/` is not visible to `COPY`. The image includes the small pure-domain
subset under `function/domain/`; `tools/sync_function_domain.py --check`
compares these files byte-for-byte with canonical source modules. Run
`tools/sync_function_domain.py` after changing those source modules. No
credentials or other application code are copied into the image.

## Prepared manifest action — not registered or development-testable

This is a review snippet only. It is not in the production manifest, not in
`ui/dist/manifest.json`, and has not been uploaded. An owner must separately
approve adding it to a development/test manifest. Workpeg's manifest actions
are offered to the model on Peg-related turns; this is not a private button
for one business. If Workpeg requires a CDN manifest update, stop and obtain
separate approval because that may expose the read-only tool across the Peg's
installations.

```json
{
  "name": "verify_roomay_inventory_read_only",
  "title": "Verify Roomay table access",
  "description": "Read canonical Roomay table metadata in this Workpeg business and return sanitized completeness only. No rows or schemas are changed.",
  "risk": "read",
  "via": {
    "table": "roomay-hotel-v1-room-types",
    "phase": "post_save_hook"
  },
  "parameters": {
    "type": "object",
    "properties": {},
    "additionalProperties": false
  },
  "returns": "Sanitized token acceptance, canonical inventory completeness, Peg/business scope match, and actor presence."
}
```

The action targets the existing canonical `room_types` alias and uses read
risk. It returns no table rows or identifiers. The other eight tables are
read by the Function only after Workpeg has authorized the alias action; the
per-call token's table permissions still apply to each GET. All table
permissions remain `700`.

## Runner compatibility

The repository's UI dependency remains pinned to Workpeg SDK **0.152.0**.
The disposable compatibility environment installed Workpeg **0.162.0** and
confirmed that `workpeg project serve --fake-cloud` and `workpeg function
test` are available. The 0.162.0 runner requires an invoke-key-aware Function
image at 0.162.0 or newer; the previous 0.157.0 image is too old. The
Function Dockerfile now uses `pegfn-base:0.162.0`; this does not alter the UI
SDK pin. Docker Desktop was unavailable during local verification, so a
container build/smoke still requires CI or a machine with a running Docker
engine.

Current official docs describe `workpeg project serve <peg> --fake-cloud` as
the local development Function runner. Its listener registers with Workpeg's
API using the developer's private `WORKPEG_PK`; Workpeg supplies a different,
per-call Function token to the handler. The dev listener may be unavailable
to the business/API (the documented response can be `404`). The Function
image now uses `pegfn-base:0.162.0`, which satisfies this runner's
invoke-key requirement. This compatibility was inspected locally but not
exercised in a Docker container because Docker Desktop was unavailable.

The 0.162.0 `function test --envelope action` fixture uses a synthetic token
and action-shaped context. It cannot prove a real Function context or
authorization. The registered manifest snippet uses `phase=post_save_hook`,
but the current dev-install docs explicitly say phase actions and real-token
agent envelopes cannot be tested in the dev runner. Unit tests exercise the
handler with a mocked Tables port only.

Do not treat `workpeg function test`, `workpeg project serve --fake-cloud`,
or a local Function container smoke as evidence of an authenticated hosted
phase action. The official dev-install guide says the engine path required to
run a dev install's Function is not available yet. This PR does not submit a
`main:<version>` Function release, install a Function, invoke an action, or
claim that a development-only phase-action route exists. Workpeg must confirm
the supported, owner-approved way to invoke this read-only action in the
Roomay AI development business without exposing a Peg-wide CDN action.

## Owner-controlled acceptance procedure — blocked, not authorized

This procedure cannot currently be executed through the documented
development Function runner: phase actions are explicitly unsupported there.
The owner must first obtain Workpeg confirmation of a supported invocation
route for this read-only action in Roomay AI, with its visibility scope
understood. Separately authorize any manifest/CDN update, Function release or
installation, and one hosted invocation. Until those decisions are complete,
do not start a Function listener, publish an action, or invoke the Function.
No hook change, table permission change, record write, or table-row inspection
is part of the proposed acceptance.

1. Ask Workpeg to identify the supported way to invoke a read-only phase
   action in a dev install, since the current guide says phase actions cannot
   be tested there. Ask whether this can be scoped to the Roomay AI test
   business without a Peg-wide CDN manifest update.
2. Review Workpeg's answer and the exact action exposure with the owner. Obtain
   separate approval for any required manifest change, release/installation,
   and one read-only invocation. Do not use `WORKPEG_PK` or start the local
   Function runner as a workaround for the documented limitation.
3. If Workpeg documents an approved invocation path, select the approved Peg
   and **Roomay AI development business** in the owner account, then follow
   only that documented procedure. The Function must use the platform-provided
   `context.token` for its two metadata GETs; never use a publishing key as a
   Tables credential or pass credentials in payloads.
4. Invoke only with empty arguments `{}`. Do not save rows or call table
   operations. Record sanitized token-acceptance, inventory, scope and
   actor-presence flags. The owner independently verifies active business
   scope. `actor_presence=unverified` does not establish staff identity.
5. On denial, unverified scope, incomplete inventory, timeout or malformed
   result, stop. Do not retry automatically, inspect rows, change permissions,
   or repair the pending audit. Retain only sanitized flags and an
   owner-held timestamp.

## What acceptance proves and leaves open

A passing invocation would prove that one platform-invoked Function context
provided a token Workpeg accepted for metadata GETs in its current Peg and
invocation business scope, and that the visible inventory matched the nine
canonical schemas/permissions. Actor presence is verified only if the
platform supplies `context.staff.email`; it would not prove a Roomay staff
department mapping, Member or Housekeeping access, row-level privacy for
other actors, request write permission, request/audit atomicity, conditional
updates, global serialization, duplicate-write protection, or persistence.
It would not inspect or change the existing pending audit. The
`NativeRequestWriter` remains disabled and unwired.

## Offline checks

Tests use fictional metadata and a mock transport. They verify two namespace
GETs only, payload cannot supply identity/scope, fail-closed permission and
schema cases, sanitized responses, canonical-domain mirror parity, and that
the production manifest remains UI-only. These are not evidence of hosted
Function invocation or Workpeg persistence.
