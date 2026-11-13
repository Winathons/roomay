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
envelope. A successful response is:

```json
{
  "authorization": "authorized",
  "inventory": "complete",
  "peg_scope": "match",
  "business_scope": "match",
  "actor_presence": "verified"
}
```

Failure results contain the same five fields with `denied` or `unverified`,
`incomplete`, and where locally known `mismatch`. No email, business UUID,
table UUID, response body, row, token, or error string is returned.

## Workpeg invocation and authorization contract

The current official [Functions documentation](https://developers.workpeg.com/docs/latest/functions/)
defines `main(context, payload)`. A platform invocation supplies `context`;
for a manifest action it includes the business, a per-invocation token, and
staff context. The token acts for the person who caused the call, is valid for
15 minutes, and is the Function's credential for Tables access. Workpeg's
Tables API authenticates it and enforces that person's table permissions
within that business and Peg. `WORKPEG_PK` is for registry/CDN submission and
the development listener; it is not a Tables API credential and is never
used by this Function.

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
`Peg-Namespace` header. Both authorized reads are required before it reports
scope matches. Then it uses the existing Function-scope attestation and
`resolve_tables_for_write()` only as a schema/permission validator; no writer
is constructed or called.

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
* `actor_presence=verified` means Workpeg provided staff context and accepted
  both reads under the invocation token. The identity is not returned. This
  does not create a Roomay department-role mapping or establish that a
  Housekeeping/Member actor is authorized.
* The inventory fingerprint binds the two returned lists to the current
  in-process attestation. It is reusable for the same inventory and is **not**
  single-use replay protection. Each invocation constructs a fresh client;
  the proof is not returned or persisted. This read-only check needs no
  replay protection and makes no such claim for future writes.

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
  "returns": "Sanitized authorization, canonical inventory completeness, Peg/business scope match, and actor presence."
}
```

The action targets the existing canonical `room_types` alias and uses read
risk. It returns no table rows or identifiers. The other eight tables are
read by the Function only after Workpeg has authorized the alias action; the
per-call token's table permissions still apply to each GET. All table
permissions remain `700`.

## Installed SDK limitation

The inspected local environment is pinned to Workpeg SDK **0.152.0**. Its CLI
offers `workpeg function new/build/run/runtime/submit`; it does not expose
the current docs' `workpeg function test` or `workpeg project serve`
development-listener commands. A manually supplied envelope to `function
runtime` is offline simulation and cannot prove Workpeg minted a token.

Current official docs describe `workpeg project serve <peg> --fake-cloud` as
the local development Function runner. Its listener registers with Workpeg's
API using the developer's private `WORKPEG_PK`; Workpeg supplies a different,
per-call Function token to the handler. The dev listener may be unavailable
to the business/API (the documented response can be `404`). The installed
0.152.0 CLI cannot run that flow. The Function image is based on
`pegfn-base:0.157.0`; its compatibility with the UI SDK pin and a future
development runner has not been live-tested.

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

1. Ask Workpeg to confirm the current supported SDK/CLI command for a local
   manifest phase action and that the dev Function listener is enabled for
   Roomay. The installed CLI does not have the current documented command, so
   first upgrade only the owner's isolated local tooling to a reviewed
   compatible version. Do not change the repository UI pin without separate
   review.
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
5. From a disposable clean project copy with only the action above added, use
   the exact command confirmed by that SDK's `--help` and Workpeg support.
   Current docs name `workpeg project serve <peg> --fake-cloud`, but this is
   **not available in the installed CLI**. `--fake-cloud` contacts real
   Workpeg services; it is not a cloud mock. Do not start it until the owner
   approves the listener and the selected business.
6. Invoke the exact action with empty arguments `{}` from a Workpeg AI turn.
   Do not invoke a table operation and do not save a row. Accept only the five
   sanitized flags. The owner separately verifies that the active business
   was Roomay AI.
7. On denial, unverified scope, incomplete inventory, timeout or malformed
   result, stop. Do not retry automatically, fall back to a developer token
   for Tables, inspect rows, change permissions, or repair the pending audit.
   Retain only the sanitized flags and an owner-held timestamp.
8. Stop the local listener using that SDK's documented procedure and remove
   the private developer credential from the process environment.

## What acceptance proves and leaves open

A passing invocation would prove that one platform-invoked Function context
provided a token Workpeg accepted for metadata GETs in its current Peg,
business and actor permission scope, and that the visible inventory matched
the nine canonical schemas/permissions. It would not prove a Roomay staff
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
