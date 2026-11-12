# Roomay — shared main-branch workflow

Updated: November 12, 2026. WOR-68 completed the migration to a main-only
workflow and removed `staging`. `main` is the GitHub default and integration
branch. This is a source-control rule; it does not mean a Peg is published or
hosted.

## Environments

| Layer | Meaning |
| --- | --- |
| `main` | Shared code and reviewed release candidate. |
| `WOR-###-...` | Issue-specific feature branch based on latest `origin/main`. |
| Workpeg `--fake-cloud` | Local dev-install server with a real Workpeg origin/session and test-table isolation. Not an offline sandbox or hosted release. |
| Local QA server | Separate loopback-only synthetic guest/staff journey; not Workpeg authentication or persistence. |
| Roomay AI business | Isolated Workpeg development business associated with the approved `roomay` Peg. Owner-only table permissions remain in force. |

## Start a change

Preserve local changes and use an isolated worktree when another branch is
active:

```powershell
git status --short --branch
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c WOR-<id>-short-feature
```

If `main` is not checked out locally, use `git switch --track origin/main`.
Never overwrite or reset dirty work. Commit only issue-scoped changes and open
a PR targeting `main`; do not commit directly to main or merge without normal
review and required checks.

## Local verification

Use the exact SDK pin in `requirements-dev.txt` (currently Workpeg 0.152.0):

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m compileall -q ui function domain tests
workpeg ui build ui/
workpeg doctor . --offline
git diff --check
```

These commands do not prove hosted data access or writes. Never run `--fake-cloud`
as CI/offline verification: it contacts real Workpeg services using the signed-in
browser session. Follow the safe, owner-operated instructions in
[WOR-25 release and tester handoff](wor-25-release.md).

## Workpeg safety

- Use Roomay AI and fictional records for development; never use customer data.
- `--fake-cloud` is a real Workpeg dev origin. The current SDK isolates dev-page
  table data under a per-business `dv-*` test namespace, separate from released
  Peg records. It may initialize test tables on first use.
- Do not put `WORKPEG_PK`, cookies or session data in code, browser bundles,
  Git, logs, screenshots or issue comments.
- Do not broaden the existing owner-only table permissions for a tester.
- Keep guest identity, department authorization, request/audit persistence and
  concurrency claims tied to their verified Workpeg/backend acceptance tests.
- Do not publish Functions, upload CDN files, release or install a Peg without
  a separately reviewed owner authorization.

## Review and release

Every PR should link its Linear issue, summarize implementation and limitations,
list exact test commands/results, include screenshots for UI changes, and request
review. Passing CI is not hosted product acceptance. Merge only after the
repository's required review/checks pass.

The Workpeg SDK can compile UI, serve a local dev install, upload public CDN
assets, and build/submit a Function. The installed CLI does not provide
`workpeg project submit` or a complete UI/manifest PegStore release command.
Do not treat CDN upload or a development installation as a complete reviewed
release. See the WOR-25 runbook for the owner/vendor action still required.

