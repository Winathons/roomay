# WOR-29 Phase B — first Workpeg table test

**Preparation only. No Workpeg API was called and no table was created for
this change.** The isolated source is ui/dev_table_setup.py; it is not
imported or registered by ui/main.py. Its route exists only in the isolated
development artifact. The release router remains unchanged.
The development controller has one possible write action: a manually clicked
create for the single room_types table. It has no row CRUD operations.

## What the SDK can verify

The pinned Workpeg 0.152.0 UI compiler supports:

- workpeg.get_tables(namespace): readable tables in the active business,
  optionally filtered by table namespace.
- workpeg.create_table(table): create a table and return its native UUID.
- workpeg.get_table(table_uuid): read a table by UUID.

The SDK takes the active business scope from the /b/<business_id>/ URL,
authenticates with the current session, and supplies the Peg-Namespace header
from the build. This isolated artifact is compiled as Peg namespace roomay.
These table helpers do not expose the business name or current user's owner
role. The screen can show the URL business UUID. A successful protected read
confirms access to the returned tables; it does not prove the URL is Roomay AI
or the current account is the owner. A readable existing table can include
owner.id, but when the table is absent that does not identify the current user.
Owner identity and business name require manual verification in Workpeg.

get_tables returns only tables the caller can read. An empty result means no
visible tables, not proof that no inaccessible table exists. The create
procedure therefore requires a separate owner-dashboard check for a hidden
room_types table. If that cannot be established, stop. Permission 700 grants
owner read/write/share and no business/public access; individual grants must
also be reviewed and are not exposed by the table-list helper.

Official docs: [Tables & Rows](https://developers.workpeg.com/docs/latest/tables/)
and [Getting started](https://developers.workpeg.com/docs/latest/getting-started/).

## Exact first-table payload

This payload matches prepare_first_room_types_creation() and the canonical
table_contracts()["room_types"]:

    {
      "name": "room_types",
      "alias": "roomay-hotel-v1-room-types",
      "namespace": "roomay_hotel_v1",
      "permission": "700",
      "metadata": {"extra": {"contract": "roomay.hotel.v1"}},
      "columns": [
        {"id": "business_id", "name": "business_id", "type": "uuid", "required": true, "position": 500},
        {"id": "entity_id", "name": "entity_id", "type": "uuid", "required": true, "position": 1000},
        {"id": "name", "name": "name", "type": "text", "required": true, "position": 2000},
        {"id": "capacity", "name": "capacity", "type": "number", "required": true, "position": 3000}
      ]
    }

alias is a write-only stable name; verification uses Workpeg's returned table
UUID, namespace, exact table name, permission, metadata, and columns. This is
table creation only: no business_id value is inserted into any row.

## Owner-operated procedure — wait for separate approval

This is a real Workpeg API path. fake-cloud is an authenticated local origin,
not a mock. Run only in the isolated Roomay AI development business, never in
a customer or production business. Do not use or generate WORKPEG_PK.

1. Sign in with the designated development owner account and select Roomay AI.
   Privately confirm its exact business UUID and owner status from Workpeg's
   own business/account interface. Do not infer these from Peg approval, a PR,
   or this screen. If either is ambiguous, stop.
2. In the owner interface, check for an existing or hidden room_types table
   under Peg roomay and table namespace roomay_hotel_v1. Review matching
   aliases and individual grants. Review visible tables in both Roomay
   namespaces too. This first-table procedure stops if any operational table
   is present; use the full planner and owner review for partial schemas.
3. After separately approved, verify a clean worktree. With the pinned SDK
   0.152.0, use the reviewed dev-install command from the repo root:

       & ..\.venv\Scripts\workpeg.exe ui serve ui/dev_table_setup.py --fake-cloud

   **Correction for the installed 0.152.0 SDK:** do not set
   WORKPEG_BIND_HOST and do not pass --peg-namespace with --fake-cloud. The
   dev-install preflight refuses both. It reads namespace roomay from the
   project workpeg.json and the Windows dev server binds to 127.0.0.1 itself.
   Windows still needs the required administrator host mapping and trusted
   mkcert setup; confirm those prerequisites with the current SDK guide first.
   Codex did not run this command. Open the HTTPS URL printed by the SDK in
   the same signed-in browser profile and navigate to
   /b/<verified-Roomay-AI-business-UUID>/dev-table-setup. Do not bypass TLS
   warnings.
4. Enter the exact business UUID. After confirming account and business in
   Workpeg, type: I VERIFIED ROOMAY AI OWNER CONTEXT. Click Inspect both
   namespaces (read only). It calls get_tables for roomay_hotel_v1 and
   roomay_requests_v1 and displays readable names, native UUIDs, permissions,
   and owner.id when returned. Successful reads do not verify owner role.
   An empty result does not prove global absence.
5. If room_types exists, the screen validates it and refuses to create another.
   Duplicate, malformed, or incompatible room_types blocks the operation.
   Any other visible table in either Roomay namespace also stops this
   first-table-only flow. Reconcile with the owner; do not alter existing data.
6. Only after the owner has separately confirmed no inaccessible room_types
   table/alias exists, type: OWNER VERIFIED NO room_types TABLE. Review the
   on-screen schema summary, acknowledge the protected-helper retry caveat by
   typing I UNDERSTAND SDK 401/403 REFRESH RETRY, and type CREATE room_types
   ONLY. Click Create room_types only (owner approval required). The sole
   application-level write is one workpeg.create_table(room_types_payload)
   call. The SDK may transparently retry after an auth failure as documented
   below; do not proceed unless the owner explicitly accepts this behavior.
7. Review the displayed fresh preflight and schema before typing the two
   creation confirmations. The separate create click re-reads both namespaces
   immediately before creation and compares the readable inventory with the
   reviewed preflight; if anything changed, it stops and requires another
   inspection. It also refuses if any table is visible. After create, it calls
   get_table(created_uuid) and freshly lists both namespaces.
   Success requires matching create response, direct GET, fresh listing, UUID,
   name, permission, metadata, and every column. No rows are created.
8. Stop on 401/403, duplicate, malformed response, schema/UUID mismatch,
   timeout, or uncertain result. The controller does not retry, delete, or
   roll back. After timeout or partial outcome, wait for the request to settle
   and have the owner reconcile inventory. Do not click Create again.
9. Record sanitized evidence only: business label, namespaces, schema result,
   authorized private native table UUID, and sanitized status/error code.
   Never capture cookies, tokens, identity payloads, or guest data. Schema
   create/read-back does not prove row persistence or staff permission denial.

## Safety boundaries and limitations

- Page mount, compile, navigation, and CI make no Workpeg calls. Regression
  tests use mocked helper responses and forbid fetch.
- Typed confirmations are operator attestations, not authentication or role
  claims. The SDK does not provide current-user owner verification here.
  Because the UI cannot verify the active user's owner role, an authorized
  owner must personally control the browser and assess the change before the
  create click. These fields cannot prevent a different authorized user from
  typing the same values; this dev-only route is not a security boundary.
- The controller creates no other table and has no row create/update/delete.
- No guest, reservation, stay, request, or production data is read or written.
- Table creation is not transactional with other table operations. Preserve a
  table after uncertain verification and reconcile; do not delete or retry.
- The installed 0.152.0 protected helper implementation can refresh the
  session and retry a protected request once after HTTP 401/403 if it did not
  refresh first. The documented table helper has no per-call switch to disable
  that behavior. The controller itself never retries a create, but this PR
  cannot guarantee a single network attempt. Before authorizing a real create,
  the owner must accept this documented SDK behavior or obtain a supported
  single-attempt alternative and verify that an initial 401/403 cannot have
  committed the table. Codex did not test this live.
- Hosted permission inheritance, individual grants, owner identity, persistence
  after reload, and second-account denial remain unverified. WOR-28, WOR-29,
  and WOR-8 remain In Progress pending the authorized hosted checks.
