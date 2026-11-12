# WOR-61 — local authentication and hotel-data boundary

## Implemented boundary

The standalone FastAPI backend no longer reads `WORKPEG_PK`, calls the
Workpeg Tables REST API, or ships the previous read-only Tables verifier.
Roomay's owner-recorded Workpeg support reply for this integration says the
developer-dashboard token is not an authorized standalone Tables credential;
the owner reported HTTP 401 on the first table read. Workpeg's general public
Tables documentation describes backend token use for a Peg's own tables, but
that does not establish authorization for this Roomay business and reader.
This branch therefore disables that path pending a supported, owner-approved
bridge.

`backend.main` installs `UnavailableHotelSnapshotReader`. Requests that need
hotel records return a generic `503 hotel_records_unavailable`; they never use
fixtures, stale snapshots or cached cross-hotel data. Existing staff OIDC,
server-side sessions, guest invitation/session checks, PostgreSQL models and
request/audit transactions are unchanged. No table permissions or hosted
Workpeg resources are changed.

OIDC verifies staff identity and selected business membership only. It is not
a Tables credential. A Workpeg Function's `context["token"]` and
`context["business"]` are invocation-scoped; the owner-recorded support reply
estimates the token lifetime at about 15 minutes. Workpeg has not confirmed a
supported external invocation boundary for this backend. Do not cache or send
that context into this persistent service, trust caller-supplied context, or
invent a Function endpoint. The hotel-data port must stay unavailable until an
approved bridge is documented and implemented.

## Exact local OIDC registration requirements

The server routes are:

- Start: `GET /auth/workpeg/start`
- Callback: `GET /auth/workpeg/callback`

The installed Workpeg SDK 0.152.0 supports OIDC authorization code with PKCE
S256. `WorkpegAuth` validates the state and verifies the ID token's signature,
issuer, audience, expiry and nonce. Workpeg requires PKCE for both public and
confidential clients; the client secret is optional for a registered public
client. The default scope is `openid profile email`. Workpeg's [Sign in with
Workpeg guide](https://developers.workpeg.com/docs/latest/sign-in-with-workpeg/)
documents these SDK behaviors and says registered redirect URIs require HTTPS,
with an HTTP exception for loopback hosts. Roomay's backend configuration
currently requires HTTPS callback and public URLs and secure cookies, so use an
actual local HTTPS origin with a trusted certificate for this app.

The owner must choose the real local HTTPS origin and port before requesting
registration. Register exactly:

```text
<ROOMAY_PUBLIC_BASE_URL>/auth/workpeg/callback
```

`ROOMAY_PUBLIC_BASE_URL` is the browser-visible origin (scheme, host and port,
without a path). `ROOMAY_OIDC_REDIRECT_URI` must exactly match that origin plus
`/auth/workpeg/callback`, and Workpeg must allowlist that exact URI. No local
origin or port is selected in this repository; never submit the placeholder.

| Setting | Source and use |
| --- | --- |
| `WORKPEG_OIDC_CLIENT_ID` | Issued by Workpeg for the registered Roomay app. |
| `WORKPEG_OIDC_CLIENT_SECRET` | Set only if Workpeg registers a confidential client and issues a secret; store it in the approved secret manager. Leave blank for a registered public client. |
| `ROOMAY_OIDC_REDIRECT_URI` | Exact registered callback URI above. |
| `ROOMAY_PUBLIC_BASE_URL` | Actual local HTTPS origin. State-changing Origin checks compare against it. |
| `ROOMAY_WORKPEG_BUSINESS_ID` | Owner-verified canonical UUID of the selected Workpeg business; OIDC must return this business. |
| `ROOMAY_HOTEL_ID` | Owner-approved canonical Roomay hotel UUID mapped to that business. |
| `ROOMAY_COOKIE_SECURE` | `true` for this HTTPS setup. |

The issuer/discovery URL is
`https://api.workpeg.com/.well-known/openid-configuration`. Public Workpeg
documentation does not describe the owner-specific client-registration
procedure. Obtain the procedure, client type, client ID, and exact callback
allowlist from Workpeg and the project owner. Do not invent client IDs,
secrets, scopes, callback hosts, business IDs or hotel IDs.

Even a successful callback does not establish hotel-table access. No real OIDC
callback or Workpeg hotel read has been verified by this branch.

## Remaining owner/vendor gates

1. Supply exact local, staging and production HTTPS origins before registering
   OIDC callbacks; do not send placeholders.
2. Ask Workpeg whether a standalone guest-service backend or Vapi webhook can
   securely invoke a Workpeg-submitted Function for a verified actor and
   business. Require documented authentication, user/business authorization,
   replay protection, token expiry and Function-context validation.
3. Keep the hotel-data adapter unavailable until that mechanism is approved
   and implemented. Never reuse `WORKPEG_PK` after the reported 401 and never
   export an invocation token into this service.
4. Preserve the existing owner-only Workpeg table permissions (`700`). No
   broadening or hosted writes are part of WOR-61.
