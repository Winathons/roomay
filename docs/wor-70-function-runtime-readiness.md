# WOR-70 - fail-closed native Workpeg Function runtime readiness

## Why this change exists

The previous generated `function/app/main.py` had the wrong entrypoint
signature (`main(event, context=None)`), and its Dockerfile ran
`pip install workpeg` over the network during the image build. Both contradict
Workpeg's published Function contract and the networkless release build.
This PR corrects those two **real packaging defects**, without enabling any
hotel operation.

Official contracts, checked on 12 November 2026:

- [How Functions Work on Workpeg](https://blog.workpeg.com/how-functions-work-on-workpeg/)
- [Functions - entrypoint and invocation](https://developers.workpeg.com/docs/latest/functions/)
- [Function base image and offline build restrictions](https://developers.workpeg.com/docs/latest/function-base/)
- [Save hooks - phases, attachment rules and AI bypass](https://developers.workpeg.com/docs/latest/hooks/)

## What is implemented

- `function/app/main.py` now exposes exactly `main(context, payload)`.
  All invocations raise the fixed, non-sensitive
  `roomay_function_not_configured` error. Malformed envelopes are rejected
  independently. No token, staff, business or request contents are logged,
  reflected to an API caller, stored or forwarded.
- `function/Dockerfile` uses the Workpeg runtime's published,
  version-specific base `pegfn-base:0.157.0`, which already supplies the
  non-root `appuser`, work directory, SDK and runtime entrypoint. There are
  no `RUN` steps, online dependency installs or extra wheels.
- Offline regressions verify the documented signature, fail-closed behavior,
  unchanged UI-only manifest and Dockerfile restrictions.
- The release router remains read-only, and `workpeg.json` still contains
  only `{"namespace": "roomay"}`. No Function, AI action or hook is
  attached or installed. A new Dockerfile alone does not install a Function.

## Version boundary - review required before any activation

ROOMAY's **UI compiler** is pinned to Workpeg SDK **0.152.0** in
`requirements-dev.txt`. Workpeg's public Function base images begin at
**0.157.0**, so the Function Dockerfile uses that separate, published base
instead of inventing a nonexistent `pegfn-base:0.152.0` image. The supported
combination of a 0.152.0-built UI Peg and a 0.157.0 Function runtime has **not
been verified in the approved developer business**. Do not submit, attach,
install or release it based on these static tests. Before activation, inspect
the installed platform capabilities, validate any required SDK alignment,
run the exact CLI build supported by that approved SDK and confirm ownership
with the lead.

## Explicit security and product blockers

The [save-hooks documentation](https://developers.workpeg.com/docs/latest/hooks/)
says ordinary API/UI row writes execute pre-save validation inline. But
**declarative Workpeg AI writes currently bypass pre-save hooks**: never
depend on a hook alone to enforce room eligibility or guest/staff privileges.
A post-save hook executes **after commit**, and its failure cannot roll back
the saved row. Neither hook provides proven cross-table atomicity, durable
request+audit idempotency, booking serialization or multi-role permission
grants. An internal HTTP `/invoke` in the Function container is **not** an
authenticated external Vapi/guest webhook entrypoint.

Operational Workpeg Tables remain the source of truth (WOR-62), with owner-only
`700` permissions unchanged. Native writes/roles are under WOR-28/29;
receptionist UI under WOR-34; external guest/OIDC access under WOR-69. Only
after those contracts are verified should the future native Function adapter
be built, with fresh privileged-session authorization and readback. Do not
attach a pre-/post-save hook, change manifest actions, widen permissions,
publish a Peg, seed live data or use developer `WORKPEG_PK` for Tables access.

## Verification and handoff

Local/offline verification:

```bash
python -m unittest tests.test_function_runtime_readiness -v
python -m compileall -q function tests
python -m unittest discover -s tests -v
workpeg ui build ui/
```

The required GitHub Actions check is the authoritative integration test.
A reviewed **Docker image build** and SDK 0.157/0.152 cross-version test
are still required before any function activation; CI passing these offline
checks alone does **not** establish a production-ready Function or legitimate
hosted invocations.
