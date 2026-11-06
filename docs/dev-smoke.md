# WOR-28: owner-operated development persistence test

The native UI compiles with SDK **0.149.1**. Offline tests exercise its generated
JavaScript with mocked table helpers. **No authenticated Workpeg request or real
persistence test was performed. WOR-28 and WOR-6 remain In Progress.**

The screen is at `/b/<business_id>/dev-smoke`. Home stays unchanged. There are no
table requests on mount, automatic writes, token fields, functions or additional
databases. No State fields persist locally: after reload the room must be re-read.

![Offline compiled screen; fictional business ID, authentication not checked](images/dev-smoke-offline.png)

Screenshot: local compiled assets, all external traffic blocked. No browser errors
or external requests observed. This is visual evidence, not an authenticated test.

## Verified SDK evidence (November 6, 2026)

- [Tables & rows](https://developers.workpeg.com/docs/latest/tables/): helper
  signatures, custom column ids, namespaces, permissions, alias uniqueness and
  whole-`data` replacement on PATCH.
- [Getting started](https://developers.workpeg.com/docs/latest/getting-started/):
  compilation reads AST without executing Python; localhost and fake-cloud behavior.
- [Data & realtime](https://developers.workpeg.com/docs/latest/data-realtime/):
  async methods, protected requests and catchable non-2xx errors.

Inspected installed files under the SDK's `workpeg/` package:

| Source | Verified behavior |
| --- | --- |
| `ui/compiler/ast_parser.py`, `_WORKPEG_TABLE_HELPERS` | `get_tables([namespace])`, `create_table(table)`, `get_rows(table_uuid, limit=..., offset=...)`, `add_row(table_uuid, row)`, `update_row(table_uuid, row_id, patch)` compile |
| `ui/runtime/workpeg-runtime.js`, table helpers | Active `/b/<business_id>/...`, session-protected requests, Peg namespace and array row responses |
| Same runtime, `_request` / `wpRequest` | Non-2xx throws HTTP-prefixed errors; protected requests may refresh a stale session and retry 401/403 once; no helper timeout/cancellation option |
| `ui/app.py`, `route` / `set_interval` | Route parameters and page-scoped timer callbacks |
| `ui/widgets/layout.py`, `Authenticated` | Mount-time session fetch/redirect; intentionally omitted so this diagnostic's requests remain user-triggered |

The manifest and built HTML declare `roomay`. The SDK supplies `Peg-Namespace`,
session cookies and business URLs. No hand-built API endpoints or developer tokens
are used. Authentication is reported only after protected table access succeeds;
the screen cannot establish the business display name, staff role or installation
status from that response. The owner verifies the business name separately.

Only 401/403 codes are classified using the inspected runtime's HTTP prefix. Raw
exceptions, server bodies, cookies, user payloads and unrelated row fields are not
rendered/logged. Other network/service/malformed-response failures use static text.

## Installation preflight — owner action

Owner-confirmed: Roomay is approved and associated with Roomay AI. Approval alone
does not establish a release, installation or working UI.

The Tables docs explicitly require installation for **developer-token** access;
a business without the installation returns 403. This screen uses the documented
**staff-session** UI path instead, whose prerequisites include authentication and
business staff membership. The docs do not establish whether this approved,
unpublished UI can be hosted/installed in Roomay AI without a Function release.
Do not extend the token rule into an unverified session-API rule.

Before live testing, the owner must confirm with Workpeg organizers:

1. Is Roomay installed in Roomay AI, and what is the verified business UUID?
2. What supported authenticated development host can serve this UI build?
3. Can this UI-only test run without a Function/Peg release, or is a separately
   reviewed release/install required? Obtain that supported process first.

Until answered, live testing is blocked. This PR publishes/installs nothing.
`workpeg ui serve ui/ --peg-namespace roomay` previews locally; it does not establish
authentication. The documented `--fake-cloud` path calls real APIs using a real
Workpeg origin. Do not use it as an automatic fallback: a separate owner decision
must approve isolated account context, hosts/TLS changes and loopback binding (the
SDK default can be LAN-visible). No fake-cloud command was run for this change.

## Exact manual persistence test after preflight succeeds

Use one designated owner/staff account, one tab and no concurrent operators/scripts.
Confirm this is the sole smoke table: a readable list may hide another owner's
records. Never paste any token/credential into the screen.

1. Sign in through Workpeg's supported staff login flow. Record the approved
   development host and verified Roomay AI UUID privately.
2. Open `https://<confirmed-roomay-development-host>/b/<verified-business-uuid>/dev-smoke`.
   This is a URL pattern, not a claimed deployed host. If unavailable, stop and
   resolve hosting/install with organizers; do not publish an unreviewed release.
3. Compare the displayed business UUID with the platform's Roomay AI context.
   Enter that UUID and type `Roomay AI single operator`. This is an operator
   safeguard, not an authentication/authorization grant or hardcoded allowlist.
4. Click **Check connection / find table**. Expect a found table or explicitly no
   *visible* table. For 401, sign in again. For 403, verify membership, installation
   and permissions; do not grant public access as a workaround.
5. If absent and the owner confirmed no earlier table exists, click **Create table
   if absent**. Expect `Roomay Dev Smoke`, namespace `roomay_smoke`, permission
   `700`, alias `roomay-dev-smoke-v1`, required text columns `room_number` and
   `status` with matching custom ids. The action checks absence again and verifies
   the created UUID through a fresh lookup.
6. Click **Create fictional Room 201 if absent**. Expect one `201` / `ready` row
   and its integer row ID. Repeat once: it should say already exists without an
   insert. Click **Read saved records** independently.
7. Reload, re-enter context and confirmation, then click **Check** and **Read**.
   Verify the same row ID and `ready` survived reload.
8. Click **Mark Room 201 dirty**. It reads fresh data, preserves every `data` key,
   changes only status and reads back the same row ID. Repeating the action when
   already dirty should send no update.
9. Reload and repeat **Check** / **Read**: same row ID, now `dirty`. Sign out/in
   through the supported platform flow and repeat to verify fresh-session reads.
10. With a second account if available, verify ungranted staff/guest/non-member
    read/write denial using the supported platform access test. **Do not click
    Create as that account**: hidden records do not prove absence. Keep 700; do
    not broaden permissions. Record unavailable second-account testing as blocked.
11. Add redacted evidence to WOR-28 and `docs/workpeg-capabilities.md`: setup method,
    SDK version, table UUID and same row ID across reads/reloads, statuses, UTC
    observation times and actual permission results. Exclude tokens, cookies, user
    identity payloads and production records. Do not mark Done until real tests pass.

## Failure, duplicate and timeout limitations

- Every action discovers the table afresh. The stable alias is documented as
  unique within a business/Peg; collisions fail without retry under another name.
  Multiple visible tables or unexpected identity/schema/permissions stop writes.
- This dedicated table allows zero or one row. `get_rows(limit=2, offset=0)` detects
  overflow; it is not general pagination. A second row, wrong room, malformed ID or
  unexpected status blocks writes. The owner must check for hidden rows/grants.
- The busy flag prevents simultaneous clicks in this page. No atomic row uniqueness
  or compare-and-insert primitive was verified. **One owner/tab only**: another
  process can race the read/insert. This is not a concurrent-safe seeder or adapter.
- Success requires matching read-back. Last success is explicitly historical. A
  failed/malformed write or failed verification locks writes for this page session;
  read-only reconciliation remains possible once the request has settled.
- After about 30 one-second UI timer ticks, all actions lock and the outcome is
  reported unknown. Browser throttling can delay the warning. The SDK has no abort
  support: a timed-out write may still complete. Late results cannot report success
  or start another write. Have the owner establish that requests settled and inspect
  saved data before reloading. **Read first; never blindly retry a timed-out write.**
- Fresh read/merge/PATCH preserves unrelated keys but is not compare-and-swap;
  another writer's changes can be lost. Single-operator scope applies to updates.
  Permission 700 alone does not prove absence of individual grants/hidden records.

## Offline verification

With the pinned SDK environment and Node 24:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q ui function domain tests
workpeg ui build ui/
git diff --check
```

The Python suite includes the 25 hotel tests plus a compiled UI test running 17
Node scenarios. It builds under ignored `build/`, executes actual generated JS and
SDK collection helpers, mocks table responses and forbids fetch. It covers no
mount-time calls, context guards, CRUD, duplicate handling, malformed responses,
401/403, failed writes, nested-data preservation, read-back mismatch and late
timeouts. These mocks verify application behavior, not hosted Workpeg guarantees.
