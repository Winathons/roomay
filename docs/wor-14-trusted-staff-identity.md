# WOR-14 Phase B — trusted Workpeg staff identity boundary (offline only)

## Why this phase exists

The Roomay AI owner has verified the fictional Room 205 hotel workflow, and an independent non-owner **Member** account returned HTTP 200 with the Workpeg hotel-table list body [] in the same business. That verifies **table-list filtering** against the current owner-only 700 tables. It is **not** evidence of authenticated department permissions, direct row denial, a functioning Housekeeping inbox, or a safe live write.

The existing domain/staff_actions.py::StaffActionGateway already validates request lifecycle and committed audit history, but it depends on an unimplemented trusted identity resolver. This phase adds a strict **server-side adapter seam** at domain/workpeg_staff_identity.py to connect a future **already verified** Workpeg sign-in to the server-maintained Roomay staff roster. It does not create a login service, install a Function, change the Reception Workspace, or perform any real Workpeg call.

## Grounding in Workpeg authentication

The current [Workpeg Sign in with Workpeg documentation](https://developers.workpeg.com/docs/latest/sign-in-with-workpeg/) provides a standard OIDC flow through workpeg.auth.WorkpegAuth. A **server** starts a new session-bound PKCE/state/nonce flow and calls complete() with the returned code and original state; complete() verifies the ID token's signature, issuer, audience, expiry and nonce. The verified identity includes:

- subject: stable opaque identity for a person **in one specific business**; use this as key
- business_id: canonical selected business UUID
- role: Workpeg membership role owner / admin / member / guest
- email/name: display details only, **not** authorization keys

**No OIDC sign-in, callback, token verification, or long-lived session was implemented by this PR.** The caller is responsible for a correct registered Workpeg OIDC client, a trusted server-held callback/session, validated token, session revocation/expiry and Workpeg membership refresh. Never pass a browser-supplied claims object or JWT payload directly to the adapter. Never send a developer token (WORKPEG_PK) to the browser.

Workpeg OIDC role does **not** imply a ROOMAY department or ROOMAY manager permissions. The roster must be server-maintained and verified for current staff membership. A personal Workpeg business and the Roomay AI business produce different subjects even for the same email.

## Adapter contract

Create TrustedWorkpegStaffResolver(verified_sessions, business_membership, hotel_mapping, staff_roster).

These four ports are **required and unimplemented**:

| Port | Required server-side behavior |
| --- | --- |
| verified_sessions.resolve_verified(session_proof) | Return only the trusted WorkpegAuth.complete-verified identity object tied to this server session |
| business_membership.is_current_staff(subject, business_id) | Re-verify current active business membership; must return actual boolean True |
| hotel_mapping.resolve_hotel(business_id) | Map that business to the canonical, trusted Roomay hotel UUID |
| staff_roster.list_staff(business_id, hotel_id) | Return a complete, current, server-owned roster for the same business/hotel |

Every roster row must provide workpeg_subject, actor_id, hotel_id, department, roles and active. Only known departments and request roles are accepted; duplicate subjects/actors, missing identities, inactive staff, wrong hotel, malformed records, and provider errors fail closed. The adapter strips Workpeg subjects from the returned Roomay directory and emits the **exact** identity dictionary that StaffActionGateway.prepare() expects. It never grants someone a ROOMAY role merely because Workpeg says admin.

The adapter must run inside a trusted server boundary. Constructing an arbitrary principal object in browser code is **not authentication**. All unit tests use fakes and prove contract behavior only.

## Data isolation and live-operation gates

Existing nine table schemas and Room 205 fictional records stay unchanged and at owner-only 700. Workpeg's [Tables & Rows documentation](https://developers.workpeg.com/docs/latest/tables/) describes individual table/row grants but **not field-level masking**. The request row contains private guest/stay and free-text fields. Do not add a table/row read grant for a Housekeeping member simply to show a filtered inbox; browser filters are not a security boundary.

Before any real staff action or inbox request:

1. Identify and review a **supported, separately authenticated backend** that can hold a Workpeg OIDC session, perform trusted staff/membership lookup and read owner-only Workpeg records while returning **only** department-safe projections. Workpeg's published Functions and WORKPEG_PK support server-to-server access for installed Pegs, but the docs do not by themselves prove a user-initiated, authenticated HTTP function endpoint is supported. Confirm the exact hosted mechanism and installation state with Workpeg; do not invent one.
2. Implement the four trusted ports with fresh authorization checks and a verified business/hotel binding, using subject rather than email. Validate staff privileges independently of Workpeg role.
3. Validate direct table and row denial for an ungranted Member using only an authorized **read-only** flow. The previously observed 200/[] is list-level evidence only.
4. Return only projection data from an authenticated server. Never share the raw request or audit row or expose WORKPEG_PK.
5. Provide a cross-writer serialization/atomicity mechanism for requests. Workpeg fingerprints are change markers, not documented CAS. Reuse the existing pending-audit → request → committed-audit reconciliation; stop on ambiguous outcomes and do not auto-retry.
6. Reconcile the owner-observed pending audit event of the fictional extra-towels request before preparing any new staff transition. Until then all actual request actions must remain unavailable, and no notification/acknowledgment can be claimed.
7. Review the real staff, wrong-department, cross-business, guest, revoked-member, malformed-roster, timeout, replay, and partial-write outcomes with independent accounts before marking the parent issue Done.

Keep the released /b/[business_id]/reception route **read-only**. The project must not publish, install a new Function, modify permissions, write Workpeg rows, or change the approved Peg in this phase.

## Offline checks

From the repository root:

    python -m unittest tests.test_workpeg_staff_identity -v
    python -m unittest discover -s tests -q
    python -m compileall -q ui function domain tests
    workpeg ui build ui/

All scenarios are synthetic. Green Python unit tests and a green build do not establish an actual Workpeg sign-in, server session, live Housekeeping access, or delivered request.

Related: [WOR-14](https://linear.app/workpeg/issue/WOR-14), [WOR-22](https://linear.app/workpeg/issue/WOR-22), [WOR-28](https://linear.app/workpeg/issue/WOR-28), [WOR-49](https://linear.app/workpeg/issue/WOR-49), docs/wor-49-authorized-staff-requests.md.
