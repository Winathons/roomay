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
The table alias is authorized before Workpeg invokes `/invoke`. **The phase
is a label, not a save trigger:** the action directly calls the Function when
Workpeg AI invokes that tool, even if the table has no save hook. This makes
the documented action route read-only without saving or changing any row. Do
not attach an actual hook. A `pre_save_hook` return may replace row data, and a
post-save hook runs only because a row was already committed; neither is
needed here. See the official [Save hooks documentation](https://developers.workpeg.com/docs/latest/hooks/).

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

## Prepared manifest action — not registered

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

The 0.162.0 `function test --envelope action` fixture uses
`phase=pre_save`/`post_save` and placeholder token `test-token`; it cannot
prove a real Function context or authorization. The registered manifest
action uses `phase=post_save_hook`, so the CLI fixture is not a positive test
of the real action path. The unit suite tests the handler with a mocked Tables
port instead.

The current official Functions documentation also says a `dev` Function
version is not installed or run on Workpeg. Only a `main:<version>` release
is reviewed and installed. This task does not submit one. Therefore an actual
test needs Workpeg to confirm its supported development listener/action path
for the Roomay AI business, plus owner approval for that path.

## Owner-controlled acceptance procedure — not yet authorized

Before running anything that contacts the Workpeg dev API, the owner must
separately approve: (a) using the development Function listener; (b) any
temporary manifest action or CDN update; (c) any testing installation or
Function activation required by Workpeg; and (d) one read-only invocation.
No hook change, table permission change, record write, Function release, or
table-row inspection is part of this procedure.

1. Confirm the approved Peg is installed for testing in Roomay AI. For a
   future listener run, use an isolated Workpeg 0.162.0-or-newer environment
   and the Function base at the same version or newer. Keep the repository's
   UI SDK pin at 0.152.0.
2. Ask whether a local development manifest action can be used without
   uploading `manifest.json` to the Peg CDN. If it cannot, stop for separate
   release/security approval; do not upload it as part of this test.
3. In Workpeg, select the approved Peg in the **Roomay AI development
   business** and privately confirm the owner account and business label. Do
   not use another business as a fallback.
4. In the owner's private PowerShell environment, configure `WORKPEG_PK`
   only if the documented dev listener requires it. Do not paste, print, log,
   or share it. It authenticates listener registration only; the Function
   must use `context.token` for the Tables GETs. Never put a token in a
   command argument or Function payload.
5. Do not proceed until the manifest action's visibility scope is approved.
   If approved, start the listener from a disposable clean project copy using
   `workpeg project serve <peg> --fake-cloud --with docker --concurrency 1`.
   Supply `WORKPEG_PK` through the owner's private process environment only;
   never place it in shell history or command arguments. `--fake-cloud`
   contacts real Workpeg services; it is not a cloud mock. This procedure has
   not been run.
6. Invoke the exact action with empty arguments `{}` from a Workpeg AI turn.
   Do not invoke a table operation and do not save a row. Record the sanitized
   token-acceptance, inventory, scope and actor-presence flags separately. The
   owner verifies that the active business was Roomay AI. An unverified actor
   field does not satisfy actor or staff-role verification.
7. On denial, unverified scope, incomplete inventory, timeout or malformed
   result, stop. Do not retry automatically, fall back to a developer token
   for Tables, inspect rows, change permissions, or repair the pending audit.
   Retain only the sanitized flags and an owner-held timestamp.
8. Stop the local listener using that SDK's documented procedure and remove
   the private developer credential from the process environment.

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
