# Workpeg table-read 401 report and OIDC registration question

Status: sanitized issue draft, based on owner-reported HTTP results and local
source inspection. No Workpeg request was made while preparing this report.

## Table API 401

**Observed by owner:** Both the original and replacement development
`WORKPEG_PK` values received HTTP `401` on the first read-only table request.
The owner separately reports that the approved Roomay Peg is installed for
testing and that all seven canonical hotel tables have matching Peg metadata,
permission `700`, and schemas. No tokens, claims, response bodies, table rows,
or personal information are included here.

**Request shape in the Roomay reader:**

```http
GET https://api.workpeg.com/v1/businesses/{business_uuid}/tables/?namespace=roomay_hotel_v1
Authorization: Bearer <server-held WORKPEG_PK>
```

The request is HTTPS, has an eight-second timeout, and does not follow
redirects. The namespace is supplied as a query parameter. The reader stops
on any non-200 response; it does not fall back to fixtures or other data.

**Local review:** This method, endpoint, bearer scheme, and namespace filter
match the current Workpeg Tables documentation's backend `WORKPEG_PK` example.
The reader also pins the business UUID in the path and validates the Peg UUID,
table permission, schema, pagination and decoded snapshot after a successful
response. The focused regression test asserts the request URL, query,
authorization-header shape, timeout and redirect behavior using a synthetic
test value. The token value is not inspected by the test report.

An HTTP 401 is returned before table metadata can be evaluated. The reported
table ownership, permission and installation evidence therefore cannot
explain or rule out a token-authentication problem. No definite local request
mismatch has been found. The exact failure stage and allowlisted code should be
captured using the existing opt-in diagnostic, not inferred from the generic
failure.

**Sanitized support summary:**

- Product: Roomay server-side read-only hotel snapshot reader.
- SDK: Workpeg `0.152.0`.
- Method: `GET` Tables collection, business-scoped path, hotel namespace query.
- Authentication: `Authorization: Bearer` with server-held `WORKPEG_PK`.
- Result: owner reports HTTP `401` for two separately issued development
  tokens on the first table-discovery request.
- Checks reported by owner: approved Peg installed for testing; seven hotel
  tables show the expected Peg metadata, permission `700`, and schema in the
  authenticated Workpeg UI.
- Local checks: endpoint, auth scheme and query match official docs; no
  redirects; fixed timeout; no writes; no fixture fallback; allowlisted
  diagnostics and mocked 401 coverage exist.
- Request to Workpeg Engineering: please confirm the current server-token
  issuance/scope requirements for this approved Peg, whether that token type
  is accepted by the documented Tables API in an installed development
  business, and what sanitized server-side check can distinguish rejected or
  expired credentials from a token with an unsupported audience/scope. Please
  also confirm whether any additional header or authorization setup is
  required. No token or response body is attached.

## OIDC client registration

Workpeg's Sign in with Workpeg documentation describes the supported
authorization-code + PKCE flow, callback validation, client ID, optional
server-held client secret, and HTTPS redirect requirement. It does not
document the dashboard steps or API for registering an OIDC client and
allowlisting a redirect URI. The repository does not contain a verified client
registration record. Do not invent a client ID or redirect registration.

Owner/provider must supply the official client-registration procedure and
confirm the exact registered HTTPS callback before Roomay activates the real
OIDC flow. If Workpeg issues a confidential-client secret, provision it through
the approved secret manager only; the documented public-client option still
requires PKCE and is not a substitute for choosing a registration mode.

## Safe next diagnostic

In the same owner-controlled PowerShell session where `WORKPEG_PK` and the
approved Peg/business identifiers are already configured, run from the repo
root:

```powershell
python -m backend.verify_workpeg_readonly --diagnostic
```

Share only the resulting sanitized JSON fields. Do not copy the PowerShell
environment, token, claims, headers, cookies, URL with identifiers, or response
body. Normal mode remains generic. Codex must not run this command against the
owner's separate session or contact the live API.
