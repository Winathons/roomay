# Roomay — shared staging workflow

Updated: November 6, 2026. The `staging` **Git branch** exists. It is **not** evidence that a Workpeg staging app or development business is deployed/connected.

## Environments and responsibilities

| Layer | What it is | State |
| --- | --- | --- |
| `main` branch | Reviewed stable release code; GitHub default | Existing |
| `staging` branch | Shared integration code; features land via reviewed PRs | Existing |
| `WOR-###-...` branches | One issue/feature at a time | Create when claimed |
| Local Workpeg UI | `workpeg ui serve ui/`, a developer-only compiler/test page | Verified locally on initial scaffold |
| Workpeg staging business | Separate **Roomay AI** business tied to approved `roomay` Peg | **Owner reports authenticated table discovery HTTP 200; schema provisioning and persistence unverified (WOR-28/WOR-29)** |
| Production Workpeg Peg | Real published customer install | **Not available/claimed** |

Never confuse a branch or localhost page with a hosted Workpeg environment.

## Git conventions

Start an issue:

```powershell
git status
git fetch origin
git switch staging                 # use 'git switch --track origin/staging' if not yet local
git pull --ff-only origin staging
git switch -c WOR-8-hotel-schema    # substitute real Linear issue ID
```

Develop and run compile checks:

```powershell
python -m pip install -r requirements-dev.txt
python -m compileall -q ui function
workpeg ui build ui/
git add <changed-files>
git commit -m "feat: describe change (WOR-8)"
git push -u origin WOR-8-hotel-schema
```

Open a **feature PR into `staging`**, not `main`. Use the correct Linear ID in the title/body (e.g., `WOR-8`), link tests and screenshots, request review, then merge after checks. A developer self-assigns the issue and starts work in Linear; the PR merge should not automatically mark an issue Done before all acceptance criteria are met.

After successful integrated validation, make one reviewed **`staging` → `main` release PR**, with release checklist and validation proof. `main` should not be the daily integration target.

## Branch settings (repository owner)

1. GitHub Settings → Rules → Rulesets (or Branches): add protections for **main** and **staging**. Prefer PR-required changes, at least one review when collaborators are available, and required UI build check only after its exact check name has successfully run. Do not lock yourself out without an admin bypass/recovery strategy; private-repo availability may depend on plan.
2. GitHub Settings → General → Pull Requests: enable **Automatically delete head branches**. Protect `staging` and `main`, so they are not feature-head branches accidentally deleted.
3. Keep `main` as GitHub default. Limit automatic deployment/publishing to a deliberate reviewed release step, **not** every staging commit.
4. Invite teammates to GitHub and Linear; grant least-privilege access. Encourage self-assigning from Backlog.

## GitHub Actions

The UI-only check (after merging the staging workflow PR) should:
- Trigger on PRs targeting `staging` and `main`, and optionally pushes to them.
- Run Python syntax validation and Workpeg Python→JS compilation with `workpeg==0.152.0`.
- Avoid starting a Workpeg server, `--fake-cloud`, live table operations, Docker publishing, or AI inference.
- Run without secrets. A failed check blocks promotion/release until investigated.

A GitHub action compiling a sample UI is **not** a verified hotel workflow or deployed staging service.

## Codex

Codex automatically reads repository-level `AGENTS.md`. Have it implement a specific claimed Linear issue on a `WOR-###-...` branch off the latest `staging` commit, then open a PR targeting staging. Codex may propose code and run local checks; do **not** give it permission for live Workpeg writes, paid inference, secrets, unreviewed merges, or deletion.

### Recommended task kickoff template

```text
Work on Roomay issue WOR-<ID> in github.com/Winathons/roomay.
Read AGENTS.md, CONTRIBUTING.md, docs/staging.md, and the issue's full description/acceptance criteria.
Use latest staging as the base, on a dedicated WOR-<ID>-... branch.
Inspect the real installed Workpeg 0.152.0 SDK and official docs; do not invent APIs.
Implement only this issue, using Workpeg native UI/tables where supported.
Never use actual hotel data, tokens, --fake-cloud, paid AI inference or production publishing.
Run syntax checks, workpeg ui build ui/, and focused tests; document exact pass/fail results.
Open a PR targeting staging, link WOR-<ID>, and summarize implementation, test proof and blockers.
Do not merge. Do not mark the issue Done until its acceptance criteria are verified.
```

## Workpeg data readiness gate

Before developing the true hotel records, **WOR-6** must demonstrate an isolated authenticated Workpeg development business:
- One fictional room row created, read, updated, refreshed and still persisted.
- Verify correct business namespace and role permissions; no privileged token in the browser.
- Record redacted evidence in Linear. No production hotel data.
- If blocked, implement UI against explicit synthetic fixtures and accurately label data source; do not invent an online integration.

## Real product release gate

- Walk-in booking persists; no false occupancy, no overlapping stay assignment.
- Guest typed request creates a real task; staff acknowledges and resolves it; history persists.
- Room marked out of service cannot be assigned to another arrival.
- All critical actions authorized and tested; guest privacy checked.
- AI/voice/PBX features disclosed as real vs. simulated, with failures shown honestly.
- No unresolved severe data correctness or privacy issue.
