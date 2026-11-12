# WOR-33 — Compiled release gate and owner acceptance

## Scope and current release decision

ROOMAY's current **UI-only**, read-only release candidate may expose only:

- `/` — informational home
- `/b/[business_id]/reception` — authenticated, read-only receptionist route

The source tree deliberately retains diagnostics and synthetic fixtures for offline
and **owner-authorized isolated** development tests. They are not customer
routes. These files must remain unreferenced by the customer release router.

The developer CRUD smoke screen formerly used
`/b/[business_id]/dev-smoke`, `roomay_smoke` and
`roomay-dev-smoke-v1`. Knowing a business UUID, entering confirmation text,
or holding developer publication credentials **does not authorize** table
operations. The production bundle must contain neither its route nor callable
privileged table CRUD logic.

## Automated guard

The `Workpeg UI build` workflow runs on pull requests and pushes to
`staging` and `main`:

1. Install pinned `workpeg==0.152.0` and run the offline suite.
2. Run `workpeg ui build ui/`.
3. Explicitly run:
   `python -m unittest discover -s tests -p 'test_release_candidate.py' -v`
4. `tests/test_release_candidate.py` builds a **new temporary compiled
   artifact**, not a previously saved `ui/dist` directory. It validates:
   - the release manifest is UI-only and retains the `roomay` namespace;
   - the complete compiled route set is **exactly** the two approved routes;
   - the emitted artifact text contains no development route, fixture or
     `roomay_smoke` table markers, even if compiler output later shifts
     away from the primary `app.js`;
   - app code calls only the currently permitted `Workpeg.wpGetTables` and
     `Workpeg.wpGetRows` helpers, not write-capable table helpers or
     Function actions;
   - credentials, private keys, and token-like patterns are not bundled;
   - synthetic guest names and IDs are absent.
5. Mutation-style regression tests deliberately insert extra/alternate routes,
   table mutation calls, smoke table identifiers, and secret markers into
   synthetic emitted JS. Each unsafe variant must fail the guard.

A failed test **blocks the GitHub Actions workflow**, not only a source-code
grep. An explicit build gate is helpful, but it does not replace GitHub ruleset
enforcement or an owner review of the exact bytes uploaded to Workpeg.

The current strict *read-only* helper allowlist is deliberately tailored to
this release candidate. When trusted hotel operations legitimately add
production writes, their authorized transport, permissions, reconciliation and
new release policy must be reviewed and tested **before** updating that
allowlist. Never simply disable the gate to get a green build.

## Manual owner review before any production release

1. Select and record the exact reviewed `staging` commit, GitHub Actions
   build run and test results. Ensure the submitted UI artifacts come from
   that commit, **not** a locally modified build or a developer diagnostic
   branch.
2. Independently build and inspect the emitted route declarations and
   application helper calls. Verify there is no alternate diagnostic route,
   Function invocation, developer token, fixture seeding or fake-cloud flow
   in the proposed release.
3. Confirm `workpeg.json` does not bind a Function/runtime or a diagnostic
   namespace. Do not submit `function/` simply because scaffold files exist.
4. Workpeg hotel tables remain owner-only `700` pending a separate **WOR-28
   hosted restricted-account test**. Verify denial to a non-owner, reception
   without grants, guest, wrong-business actor and unauthenticated session
   using vendor-supported mechanisms. Do not widen permissions just to satisfy
   a UI test. If a test identity or supported mechanism is unavailable,
   record **unverified/blocked**.
5. The owner must obtain Workpeg's supported release/publishing process
   (WOR-25), approve the immutable artifact, and separately approve
   installation. Neither `workpeg cdn submit` nor
   `workpeg ui serve --fake-cloud` is proof of a complete approved release.
   Fake-cloud connects to the real service and is allowed only for explicitly
   authorized isolated Roomay AI development testing.
6. Repeat the release audit if the Peg/compiler/manifest/deployment path
   changes. A GitHub test is not an independent guarantee about an artifact
   assembled or uploaded outside that path.

## Evidence and handoff

- Build and automated checks: `tests/test_release_candidate.py` and
  `.github/workflows/workpeg-ui.yml`.
- Existing authorized diagnostics: `docs/dev-smoke.md`; not a published route.
- Source-boundary acceptance: `docs/wor-25-release.md`.
- Real restricted-account Workpeg permission evidence: owner-led WOR-28.
- Access policy and negatives: WOR-22 / `docs/roomay-access-model.md`.

**Done criteria:** compiled-route/CRUD isolation confirmed on the exact
release candidate, CI green, reviewer acceptance, and required independent
hosted Workpeg role/permission and publication checks verified. Until then
WOR-33 remains **In Progress**, even if the PR merges or offline tests pass.
