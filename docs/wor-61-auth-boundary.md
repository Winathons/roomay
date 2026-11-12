# WOR-61 — Workpeg authentication boundary and OIDC integration decision

**Status:** Proposed integration boundary; vendor confirmations and hosted acceptance outstanding.  
**Date:** 2026-11-12  
**Scope:** Standalone guest backend authentication/Workpeg access only. Request/audit source of truth belongs to WOR-62.

## Decision and authoritative evidence

The owner-recorded direct Workpeg support reply in [WOR-61](https://linear.app/workpeg/issue/WOR-61) (2026-11-11) supersedes contradictory public documentation for this integration:

1. `WORKPEG_PK` from the developer dashboard is for Peg publication/development, **not** a standalone backend's Tables API access. Repeating token resets or changing permissions will not fix the observed backend HTTP 401.
2. An authenticated **Peg UI** can call `workpeg.get_rows` and related helpers in its current signed-in user's business scope.
3. A **Workpeg-submitted Function** receives `context["token"]` and `context["business"]` per invocation. That user/business-scoped token lasts about 15 minutes. It must never be cached, transported outside an approved invocation boundary, stored as a reusable backend secret, or treated as a global service identity.
4. Workpeg **OIDC** requires vendor app registration and establishes staff identity/business membership, **not** Tables API authorization.
5. There is **no** long-lived standalone server Tables API key supported by the vendor.

No wider access or external Function trigger has been confirmed. This ADR does **not** authorize deploying, publishing Functions, changing table permissions, or making hosted writes.

## Presently broken path and safe correction

Draft [PR #37](https://github.com/Winathons/roomay/pull/37) currently has:
- `backend/config.py`: a mandatory `WORKPEG_PK`.
- `backend/main.py`: constructs `WorkpegHotelReader(..., workpeg_pk=settings.workpeg_pk)`.
- `backend/workpeg_reader.py`: sends that developer token as a bearer token to Workpeg Tables API.
- `.env.example` and `docs/guest-service-backend.md`: instructions that mistakenly present `WORKPEG_PK` as supported external server read access.
- `GET /auth/workpeg/start` and `GET /auth/workpeg/callback`: draft OIDC endpoints with offline mock tests, **not** a real registered client/callback.

**Required follow-up change (separate owner-coordinated PR or explicitly authorized edit of PR #37):**
- Delete the unsupported developer-token Tables reader from the active backend startup path; remove `WORKPEG_PK` as a runtime prerequisite. Update example configuration, verifier/CLI assumptions, documentation and affected tests together.
- Keep a narrow **hotel snapshot port** for the application, but return a stable **unavailable/unsupported** state until an official authenticated delivery mechanism is approved and integrated. Never fall back to fixtures or cached cross-hotel data, and never report a request as persisted merely because an upstream read failed.
- Do not substitute the OIDC access/ID token for a Tables credential.
- Do not import a Workpeg Function's context token into the persistent guest API, retain it after the invocation, allow callers to construct or override trusted context, or infer authorization from the public request body.
- Continue to deny all unsupported guest operations, and retain the existing owner-only `700` table policy.
- Keep PostgreSQL versus Workpeg request/audit ownership undecided until **WOR-62** receives explicit approval; no dual writer or implicit sync.

No runtime code changes to draft PR #37 are made by this document-only branch.

## Supported/trusted access matrix

| Caller/runtime | Workpeg identity/credential | Hotel records | Remaining verification |
| --- | --- | --- | --- |
| Signed-in Workpeg Peg UI | Workpeg browser session bound to business | Scoped `workpeg.*` helpers | Role/permission negatives under WOR-28 |
| Workpeg-submitted Function | Invocation-only `context["token"]` plus verified `context["business"]` | Only authorized per-invocation data actions | Official trigger semantics, role restrictions, context authenticity, cross-business denial |
| ROOMAY standalone staff backend | Workpeg-registered OIDC authorization code login | **No direct Tables entitlement** | Real callback and safe authorized bridge, if vendor supports |
| Public guest portal / Vapi webhook | Separate stay-scoped invitation/session or verified caller authorization | **No general Tables access** | Approved bridge, verified stay, explicit confirmation and audit |
| Developer/publishing process | `WORKPEG_PK` | **Not** a standalone Tables client | Retain only for the vendor-approved development/publish workflow |

## OIDC registration request (owner must supply exact URLs)

Send the following to the Workpeg team only after the project lead selects a proper guest-backend deployment host (not the unrelated Remi TTS Railway host).

- **App display name:** ROOMAY — Hotel Staff / Guest Service Backend (proposed; confirm with owner).
- **Client type:** Server-side confidential OIDC authorization-code client, using server-protected client secret and PKCE if supported by the SDK/provider. Confirm client-type support with Workpeg.
- **Scopes:** `openid profile email` only unless Workpeg explicitly requires additional scopes for verified membership claims.
- **Staging callback:** `https://<owner-approved-staging-backend-origin>/auth/workpeg/callback` — placeholder; must become an exact URL.
- **Production callback:** `https://<owner-approved-production-backend-origin>/auth/workpeg/callback` — placeholder; must become an exact URL.
- **Local callback:** `https://<owner-approved-local-HTTPS-origin>/auth/workpeg/callback` — placeholder; vendor must confirm support. No insecure fallback.
- **Registration outcome:** client ID delivered by approved secret manager, secret only to backend runtime, issuer/discovery metadata and exact scope/claim semantics recorded without secrets.
- **Question:** What verified identity/business-membership claims are returned, and what is the session/revocation behavior? Can the client be confidential with PKCE on the existing SDK 0.152.0?

**Do not send placeholder URLs as registration values.** Await exact owner-selected origins. The endpoints already exist as a draft; this is not evidence that Workpeg registered them.

## Vendor Function invocation question — blocking

> Does Workpeg offer an officially supported, authenticated means for a standalone guest-service HTTPS backend or a Vapi webhook to invoke a **Workpeg-submitted Function** on behalf of a verified staff actor in a specific Workpeg business? If so, please supply the documented entrypoint, authentication and invocation trust boundary, caller-to-user/business authorization rules, replay/idempotency and expiration behavior, Function context validation, and whether it can serve a separately stay-verified guest request without granting the guest a staff identity. If not supported, please confirm that external callers cannot use Function context tokens or standalone Tables APIs.

No vendor response is on record yet; treat this as **blocked**, not as permission to invent a webhook or mint a Function token.

## Offline and hosted acceptance matrix

| Test | Expected result | Evidence state |
| --- | --- | --- |
| Misusing developer PK on standalone Tables API | Unsupported, retired from architecture; no further token experiments | Vendor-confirmed |
| Malformed, spoofed or missing Function `context` | Fail closed; never trust caller-supplied business/token | Pending supported Function boundary |
| Expired Function token or wrong business | Denied; no silent retry with developer token | Pending hosted vendor-approved test |
| Unauthorized department, wrong hotel or role | Denied server-side, including within an otherwise valid OIDC session | Offline contracts exist in PR #37; hosted test pending |
| OIDC state/nonce/PKCE mismatch, invalid callback | Fail closed with no staff session | Offline mocked tests; registered OIDC callback pending |
| Revoked Workpeg membership or expired Roomay session | Re-authenticate/deny according to documented revocation window; do not claim immediate Workpeg revocation without proof | Hosted test pending |
| Guest invitation expired/replayed, checked out, or wrong stay | Deny with no guest data exposure | Offline mocked tests in PR #37; hosted read path blocked |
| Workpeg service loss/timeout | Explicit unknown/unavailable; no fictional snapshot, ticket or confirmation | Offline failure tests; hosted read path blocked |
| Real authorized hotel snapshot through official path | Read after independent session/reload with verified owner-only table scope | **Not demonstrated** |
| Secret handling | No credentials in git, logs, screenshots, Linear, PR or browser | Required review |

The code in PR #37 has SQLite-backed tests and a mock Workpeg identity provider; that is *not* proof of an OIDC registration, authentic Workpeg Function invocation or server hotel-record reads.

## Ownership, gates and delivery

1. **Owner:** Confirm backend hosting origin(s), allowed vendor registration details, and send the exact Function invocation question; approve any production-bound Workpeg identity/role/table operation.
2. **Aliameen (WOR-61):** Implement the fail-closed removal of the unsupported standalone Tables path only in a separately reviewed, owner-coordinated backend branch; test wrong-business/role, spoofed/expired context, logout/session expiry and server loss.
3. **Owner and Aliameen:** Verify actual OIDC callback using a vendor-registered client and an authorized synthetic staff identity; record sanitized success/denial evidence.
4. **WOR-62:** Decide authoritative request/audit writer, consistency bridge, retries and reconciliation in a separate architecture approval. Do not merge PR #37 until these gates pass.
5. **Review and release:** PR to `staging`; no hosted writes, publication, role relaxation, deployments, secret changes or automatic merge.

**Current decision:** Direct standalone Workpeg Tables access using `WORKPEG_PK` is **rejected**. Workpeg Function access from an external backend and live OIDC are **not verified**. Guest-to-staff workflow remains blocked until supported authority and persistence are demonstrated.
