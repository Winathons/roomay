# WOR-69 — WorkPeg integration audit

14 November 2026. **Offline investigation only; external dependency unresolved.**
[WOR-69](https://linear.app/workpeg/issue/WOR-69) remains Backlog.
Baseline: `origin/main` at `4aa081a`; isolated branch
`WOR-69-integration-audit`. No runtime, contracts, manifest or permissions changed.

## Decision and evidence boundary

The [approved 14 November project](https://linear.app/workpeg/project/roomay-workpeg-hospitality-hackathon-7b7a7ce4b3b9)
supersedes historical booking/voice/guest-web plans. Implement verified guest
stay-code access → scoped WorkPeg AI guidance → guest-confirmed request → one
canonical WorkPeg request and committed audit → receptionist assignment/status
update → guest saved-status readback. WorkPeg Tables are the sole operational
store. Preserve dormant prototypes; do not activate them as a fallback.

Architecture discovery is partly resolved. Official documentation supports
native staff-session Tables operations, platform-invoked Functions, and an
external queue collected by a signed-in native Peg. Current references also
show constrained inbound keys. None proves Roomay's hosted guest authorization,
request/audit consistency or independently authenticated end-to-end acceptance.
Older WOR-61/62 documents contain historical draft/merge and ownership language;
their completed offline/decision phases transferred live blockers to WOR-69.

Sources read on this date:

- [OIDC guide](https://developers.workpeg.com/docs/latest/sign-in-with-workpeg/),
  [Tables guide](https://developers.workpeg.com/docs/latest/tables/), and
  [Functions explainer](https://blog.workpeg.com/how-functions-work-on-workpeg/).
- [formnow source](https://gitlab.com/workpeg/formnow), inspected at commit
  `82d07893d6f8712640a2ad6393acca64e0d458c4`: `docs/build-your-own.md`,
  `peg/ui/pages/forms.py`, and `api/core/inbound.py`.
- Installed `workpeg==0.152.0` authentication source and UI exports. Online
  latest docs and formnow's API pin `0.159.0` are not versioned guarantees for
  Roomay. `sso.approve` exists in 0.152.0; `workpeg.create_inbound_key` does not.
  Symbol presence alone is not a working compiled/browser integration test.

## Supported patterns and trust boundaries

| Boundary | Verified implementation/documentation | Limit |
| --- | --- | --- |
| Native Peg → Tables | Signed-in staff session, business scope and table ACLs; current Reception reads via native helpers | Owner-reported installed readback; no independent hosted retest here. Existing `700` permissions grant no regular-member access. |
| Platform → Function → Tables | Real invocation supplies actor/business and a short-lived token, documented at about 15 minutes | Do not export/cache the token, accept browser-supplied context or invent a public invoke endpoint. Inbound hooks are a distinct actor and receive no token. |
| External staff OIDC → Roomay | SDK authorization code + S256 PKCE; signed ID-token verification; subject/business identity | Identity does not grant Tables rights, Roomay department privileges, or guest active-stay authorization. |
| formnow external queue → native Peg | Staff signs in through in-page SSO; page-open/manual sync leases items, writes native rows, then acknowledges | Delayed collection, not background delivery or Roomay service-request/audit integration. ACK trusts the collecting Peg's readback. |
| Optional external inbound key → one table | Current reference documents operator-granted `inbound` scope, own-origin writer minting, binding via `whoami`, encrypted storage, revocation and idempotent add-row calls | Write-only for one table; no read/update/delete or general Tables credential. Not a request+audit transaction, not guest identity, absent helper in 0.152.0. No Roomay key/grant verified or authorized. |

`WORKPEG_PK` is a publishing/development credential, not this standalone
backend's Tables key. OIDC ID tokens and invocation tokens are not substitutes.
Inbound keys are a separately documented constrained capability, not an exception
authorizing developer-token access. Do not generate any credential for this audit.

## Existing adapters: implemented versus provisional

- `backend/app.py`: dormant prototype has browser-bound hashed OIDC state,
  stored nonce/verifier, ten-minute callback lifetime and single-use state
  consumption before token exchange. It checks selected business/member role
  and active local subject-to-hotel/staff bindings before issuing a local session.
  On each request it checks local session expiry/revocation and active roster/
  hotel binding. **It does not refresh WorkPeg membership on every request**;
  the cached login role cannot establish immediate provider-side revocation.
- `backend/config.py`: exact HTTPS origin/callback matching, secure-cookie and
  canonical business/hotel UUID checks. Owner must select real origins and client
  registration. Repository requirements omit `PyJWT[crypto]`, which installed
  SDK token verification requires; mocked backend auth tests conceal this gap.
  Add an approved dependency and real signed-token regression tests in a separate
  runtime PR before treating OIDC setup as reproducible.
- `domain/workpeg_staff_identity.py`: resolver requires trusted verified-session,
  **fresh membership**, hotel mapping and private staff-roster ports. It rejects
  claim dictionaries and does not derive Roomay admin rights from a WorkPeg admin
  role. These trusted production bindings are not wired; mock-port passes do not
  prove membership revocation against WorkPeg.
- `domain/workpeg_function_tables.py`: invocation-only fixed-host/no-redirect
  REST adapter, safe 401/403 errors, expected business and Peg checks. Local JWT
  decoding rejects mismatches; it does not authenticate the token. Actual API
  authorization is trusted only inside a real platform invocation. No such
  invocation was performed. `function/app/main.py` refuses every operation;
  `workpeg.json` does not activate it.
- `domain/workpeg_writer.py`: disabled coordinator sequences pending audit,
  request, committed audit and independent reconciliation. Requires trusted actor
  context and an all-writers serialization guard. Those are unresolved platform
  integrations; process-local locks and opaque fingerprints are insufficient.
- `public_intake/`: test-only application factory, isolated booking-interest
  queue and generic collector ports. No real OIDC resolver or native writer is
  wired. HTTP 202 explicitly says `queued_pending_staff_collection` and
  `workpeg_delivery_confirmed:false`; uncertain writes/readback are not ACKed.
  This deferred booking prototype is not the approved AI service-request route.
  The standalone backend's PostgreSQL ledger is dormant and not synchronized
  with WorkPeg. Never activate it as a competing operational writer.

## Exact confirmations and dependency handoffs

| Owner | Required answer/evidence before activation |
| --- | --- |
| WorkPeg + project owner (WOR-69) | Select supported **AI guest** action/ingress and status-read path, actor/business/verified-stay binding, replay/expiry limits and deployment review. A generic external Function endpoint remains unverified; do not ask for another explanation of the already documented pull pattern. |
| Owner + WorkPeg OIDC registration | Confirm client type, exact approved HTTPS origins and `/auth/workpeg/callback` URIs, scopes, issuer/audience, subject/business/role semantics, supported membership revalidation/revocation window and client-secret delivery channel. Supply no placeholder registrations. Real registration/callback remains unverified. |
| WorkPeg + WOR-28/29 | Prove actual native/invocation actor ACLs, complete canonical reload readback and cross-business/non-owner denials. Confirm transaction/CAS/uniqueness or serialization covering **all** writers; document recovery for request/audit partial writes. Preserve `700`; no grants inferred. |
| WOR-34 | Wire separately reviewed authorized receptionist assignment/status UI to the canonical writer; current compiled UI remains read-only. |
| WOR-65 | Implement the approved delivery adapter and idempotent reconciliation/readback using the single canonical store after the above gates. Existing transport experiments on other branches are not mainline or hosted evidence. |
| WOR-77 | Consume the other developer's reviewed versioned identity/action/request/status contracts; coordinate interface questions without editing their files or branch. |
| WOR-89 | Witness independent guest → AI → request/committed audit → receptionist → guest saved-status acceptance and denials. No mock-only signoff. |

If inbound delivery is proposed, WorkPeg must confirm a compatible SDK/version,
operator grant, canonical target table, idempotency retention and revocation
semantics, and how a verified guest action plus audit can be secured. One-table
append does not resolve the canonical two-table or status-read requirement.
Any SDK upgrade, key issuance, Function install, scope/permission change or
external host activation requires separate reviewed owner authorization.

## Offline verification

Linux Python 3.12.14, Node v24.22.1, WorkPeg 0.152.0. No real credentials,
WorkPeg data calls, live Functions or OIDC registration used. Synthetic tests
use SQLite/mocked transports; PostgreSQL results are not claimed here.

| Exact command | Result |
| --- | --- |
| `PATH="$PWD/.venv/bin:$PATH" python -m unittest tests.test_backend_config tests.test_guest_backend tests.test_workpeg_staff_identity tests.test_workpeg_function_tables tests.test_workpeg_writer tests.test_public_intake -v` | 73 tests passed, no skips |
| `.venv/bin/python -m pip install 'PyJWT[crypto]'` | Test environment only: PyJWT 2.15.1, cryptography 50.0.2; requirements unchanged |
| `PYTHONPATH="$PWD" .venv/bin/python /workspace/work/wor69_offline_probe.py` | 6 ad hoc probes passed; scratch harness outside repository, not a committed regression suite |
| `git diff --check` | Passed |

The six probes checked fresh state/nonce/verifier and S256 challenge; mismatched
state/missing code before exchange; exchange callback/verifier/grant fields and
mocked provider refusal; locally RSA-signed valid versus expired/wrong-nonce/
wrong-audience/wrong-issuer tokens; browser-bound callback/wrong-state/replay;
and single-use state after provider rejection. All HTTP exchanges were mocked
or in-process. Initial probe run had one harness failure (mock raised a generic
error, correctly producing 503 rather than the expected 401); corrected to
`WorkpegAuthError`, then all six passed. No runtime correction was made.

The 73 existing tests cover local session expiry/revocation, cross-business and
unauthorized staff/department denial, forged resolver inputs, Function 401/403,
unsafe pending writes, uncertain outcomes, idempotent reconciliation, queue
leases and false delivery prevention. PKCE challenge construction/exchange was
checked locally; real provider enforcement of a wrong verifier, real code replay,
signature/JWKS rotation and immediate provider-side revocation remain unverified.

## Next implementation and acceptance sequence

1. Record vendor answers and owner-selected identity/ingress decisions; keep
   WOR-69 Backlog until the external dependency is actually resolved. Confirm
   SDK compatibility before changing dependencies, manifest or runtime contracts.
2. In a separately reviewed runtime PR, add auth dependencies/signed-token
   regression coverage and wire trusted membership/roster/session adapters with
   an explicit revocation policy. Reuse WOR-77 contracts; do not infer guest
   authorization from staff OIDC or a room number/QR alone.
3. After WOR-28/29 guarantees, implement WOR-65's one authorized writer and
   reconcile partial/ambiguous writes without blind retry. Wire WOR-34 to it,
   then scoped AI room-facts/status projections. Report pending until canonical
   request **and committed audit** are independently read back.
4. With separate owner approval and fictional active-stay data, verify real
   OIDC callback and rejected state/nonce/verifier/replay/expired/revoked cases;
   verify allowed roles plus wrong business/room/guest/department denial.
5. WOR-89: independently refresh guest and receptionist sessions, verify one
   request and audit despite duplicates, staff assignment/status persistence,
   guest saved-status readback, and outages/partial-write recovery. Follow
   [release approval and rollback gates](wor-25-release.md) before any release.

Fallback decisions requiring approval: delayed staff pull and disclosed service
latency (unsuitable for an implied emergency guarantee); SDK upgrade/inbound
capability adoption; any new external guest entry or hosting. No silent fallback
to PostgreSQL authority, booking, voice, standalone guest-web, broader ACLs or
fabricated delivery. When capability is absent, remain unavailable/pending and
provide an owner-approved human contact path rather than promise delivery.
