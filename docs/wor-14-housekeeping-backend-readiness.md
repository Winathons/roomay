# WOR-14 Phase C — Housekeeping backend readiness

## Result

This change adds an offline, server-boundary service facade for a future
Housekeeping request inbox and action endpoint. It composes the existing
`TrustedWorkpegStaffResolver`, `project_staff_inbox`, and
`StaffActionGateway`. It does **not** provide a hosted endpoint, Workpeg table
reader, authentication/session implementation, or persistence writer. The
facade can be exercised with deterministic ports, but no Housekeeping user can
use it against Workpeg yet.

All action plans remain unpersisted. Reception Workspace remains read-only.
No table, record, permission, manifest, or release route was changed. In
particular, owner-only `700` table permissions remain untouched and the
existing fictional Room 205 records are not read or modified by these tests.

## Workpeg capability evidence

The installed environment is pinned to Workpeg SDK `0.152.0`. The official
documentation and installed SDK establish these supported mechanisms:

| Capability | Verified behavior | What it does not establish |
| --- | --- | --- |
| Sign In with Workpeg | `WorkpegAuth` provides an OIDC authorization-code flow; the server must preserve state/nonce/PKCE and validate the callback. A verified identity includes a business-scoped `subject`, `business_id`, and Workpeg membership `role`. | It does not create a Roomay department role, trusted hotel mapping, or a long-lived Roomay session automatically. |
| Tables | Workpeg table access is business-scoped and uses the authenticated session/permissions. | It does not document field-level row masking for returning only selected service-request fields. |
| Functions | A Function receives platform `context` and caller payload. The documented staff context exposes email and optional extra fields; a stable subject and user-session propagation are not guaranteed by the contract inspected here. `WORKPEG_PK` is a server-side Peg credential for installed Peg access. | The docs/SDK inspected do not establish a generic authenticated HTTP endpoint from the compiled Python UI, a per-user delegated table session inside a Function, or that `WORKPEG_PK` is available to an independently hosted service. The local runtime `/invoke` handler has no authentication and is not a production boundary. |
| Compiled Python UI | It supports Workpeg UI table helpers in the active business session. | The installed compiler explicitly rejects `RunFunctionAction` in compiled Python UI. Schema UI's function action is a separate mechanism and does not establish an authenticated receptionist-to-function call. |

Sources: [Workpeg OIDC documentation](https://developers.workpeg.com/docs/latest/sign-in-with-workpeg/),
[Functions documentation](https://developers.workpeg.com/docs/latest/functions/),
[Tables documentation](https://developers.workpeg.com/docs/latest/tables/),
[Schema UI documentation](https://developers.workpeg.com/docs/latest/schema-ui/).
The SDK source was inspected locally at `workpeg/auth.py`, `workpeg/context.py`,
`workpeg/runtime.py`, `workpeg/ui/compiler/ast_parser.py`, and
`workpeg/ui/actions.py`.

## Implemented boundary

`domain/housekeeping_requests.py` accepts only server-injected ports. On every
call it resolves the opaque session proof through the trusted identity adapter,
requires current membership and business binding, checks a server-maintained
staff directory entry is active and belongs to the mapped hotel and
Housekeeping department, and ignores browser-provided identity fields. Inbox
reads require a complete, business/hotel-scoped inventory and reject malformed
or duplicate request identities. Existing policy projection filters out other
departments and excludes guest, stay, hotel, idempotency, and audit-linkage
fields. Description text is still operational content and can itself contain
personal data; it must be handled as sensitive data by any future host.

The action facade permits only acknowledge, start-work, resolve, and escalate.
It delegates lifecycle and committed-audit checks to `StaffActionGateway`,
does not return its internal plan, and reports `persisted=False`. The existing
gateway's expected version and fingerprint are stale-read checks, not an
atomic compare-and-swap. Its pending-audit/request/committed-audit sequence
still requires an externally verified serialization mechanism and read-back
reconciliation before any write can be enabled.

## Blocking platform questions

Do not expose this facade as a network service or wire it to live tables until
Workpeg confirms a supported deployment and authentication pattern answering
all of these questions:

1. What supported server-side endpoint can a compiled Python UI invoke while
   carrying an authenticated Workpeg user session?
2. Does that invocation provide a stable, business-scoped Workpeg subject and
   the selected business ID, and how is the identity cryptographically
   verified by the receiving server?
3. How can a backend recheck revoked business membership on every request?
4. Can a supported server-side component read the existing owner-only tables
   while preserving a user identity boundary? Is access via `WORKPEG_PK`
   restricted to an installed Peg, and what exact installation/scoping rules
   apply to these tables?
5. Can that component safely return a field-minimized projection without
   exposing raw rows or broadening the current `700` permissions?
6. What supported lock, transaction, or compare-and-swap primitive serializes
   request and audit-row writes across simultaneous writers? Fingerprints
   alone are not proof of atomicity.
7. How are Function review, publication, installation, secrets, and invocation
   authorization handled for this exact approved Peg and development
   business?

These require Workpeg provider clarification and owner review. The local SDK's
Function packaging commands are not sufficient evidence for a secure online
request path. No Function was built, submitted, published, or installed here.

## Required hosted acceptance after clarification

After a reviewed backend mechanism exists, use separate authorized test
accounts and synthetic records to verify: a current Housekeeping member can
read only Housekeeping-safe projections; Maintenance and Reception members
cannot read that inbox; revoked membership is denied promptly; cross-business
requests are denied; direct table and row requests remain denied under current
permissions; no guest identifiers or audit internals are returned; and an
unreconciled/pending audit blocks every action. Then verify serialization,
idempotency, partial-write reconciliation, persisted audit read-back, and
guest-facing status projection. Do not use the owner's session as a substitute
for department authorization.

No live verification was performed in this phase. The complete Linear issue
descriptions were unavailable in the connected workspace; implementation was
bounded by the repository contracts and task acceptance criteria provided.
