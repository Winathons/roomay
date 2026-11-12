# WOR-71 - Offline Workpeg Function container build smoke

This is a **package verification** for ROOMAY's inactive Function, not an
installed Workpeg Function, approved hotel write path or hosted integration.

## What CI checks

The repository's existing required `Roomay UI Check` workflow:

1. Compiles and tests the Workpeg UI and hotel contracts as before.
2. Runs `docker build --network=none --pull --progress=plain -t
   roomay-function-smoke:ci ./function` on a Linux GitHub Actions runner.
   This may pull the documented Workpeg base image from the container
   registry, but gives **Dockerfile build commands no network**. No
   application dependency downloads are permitted.
3. Starts a short-lived local Python process **inside the built image** with
   Docker networking disabled. It checks the packaged
   `main(context, payload)` signature and asserts the fixed
   `roomay_function_not_configured` rejection for several fictional
   invocation envelopes. It never passes a credential, real business ID or
   actual person/guest record.
4. Leaves the deployed app untouched. The user-facing `workpeg.json`
   continues to declare only `{"namespace": "roomay"}`; no Function,
   hooks or AI manifest actions are installed or activated.

## Source and runtime boundaries

The real Function runtime base used by `function/Dockerfile` is Workpeg
`pegfn-base:0.157.0`. The repository's compiled Workpeg UI SDK remains
`workpeg==0.152.0`. This CI check verifies that the **base image can build**
and the **local packaged entrypoint rejects requests**. It cannot prove
that a Function using 0.157.0 works with an installed 0.152.0 UI Peg, that
the vendor will approve/install that version, or that any user possesses
the required Workpeg table permissions.

The container does not make requests to Workpeg APIs or Vapi. A local
`/invoke` is an internal Function runtime endpoint, not authorization
for an external guest webhook. The developer dashboard `WORKPEG_PK`
cannot be used as a general Tables API token, and Function
`context["token"]` is invocation-scoped.

## What remains

- WOR-28/29: Owner-approved, authenticated, business-scoped hotel Tables
  writes, staff roles, guarded concurrency and readback.
- WOR-34: Actual Reception UI integration.
- WOR-69: Vendor-supported external guest/Vapi ingress and OIDC.
- WOR-25: Owner-reviewed installation/release path and compatible Function
  version; no submission or release is authorized here.

A green CI status **must not** be described as a hosted Function proof.
If the public base registry fails to pull, or the packaged entrypoint is
not importable, the workflow fails visibly rather than bypassing the
verification step.

## Run locally (optional, offline execution)

```bash
docker build --network=none --pull --progress=plain -t roomay-function-smoke:ci ./function
docker run --rm --network none --entrypoint python roomay-function-smoke:ci -c 'from app.main import main; print(main.__name__)'
```

The second command imports without invoking. The required GitHub workflow
contains the additional synthetic refusal assertions.
