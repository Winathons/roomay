# Historical Workpeg table-read 401 and OIDC registration note

This report records the owner-reported 401 that led to the WOR-61 boundary
decision. No token or live Workpeg request was used by this implementation.

## Observed table-read failure

The owner reported that two separately issued development `WORKPEG_PK` values
received HTTP 401 on the first business-scoped, read-only Tables request. The
owner also reported that the approved Roomay Peg was installed for testing and
that seven hotel tables showed expected metadata and permission `700` in the
authenticated Workpeg UI. Those checks do not establish that an independent
backend is authorized to read the tables.

Workpeg's general Tables documentation currently describes a developer token
for backend access to a Peg's own tables in businesses where that Peg is
installed. The owner-recorded support reply for the Roomay integration says
this token is not an authorized standalone Tables credential. The account-
specific result and support response are recorded in [WOR-61](https://linear.app/workpeg/issue/WOR-61);
they do not change Workpeg's general documentation. The standalone reader and
diagnostic command have been removed from the Roomay backend pending an
approved alternative. Do not retry tokens or broaden permissions to resolve
the 401.

## OIDC client registration

Workpeg's [Sign in with Workpeg guide](https://developers.workpeg.com/docs/latest/sign-in-with-workpeg/)
documents authorization code with PKCE, ID-token verification, and public or
confidential clients. It does not document the owner-specific dashboard
registration steps or callback allowlist procedure. See
[WOR-61 local authentication](wor-61-local-auth.md) for the exact values the
owner must select and obtain. No client ID, client secret or registered
callback is present in this repository.

## Workpeg Function boundary

Workpeg Functions receive invocation context, but no supported external caller
contract for this guest backend has been confirmed. An invocation-scoped
context token must not be cached or passed into the persistent API. Obtain a
documented invocation and authorization boundary from Workpeg before
implementing a bridge. No Function was built, submitted, published or
installed for this change.
