# Contributing to Roomay

Roomay is a Workpeg-native hotel operations and AI guest experience application. The [Roomay Linear project](https://linear.app/workpeg/project/roomay-workpeg-hospitality-hackathon-7b7a7ce4b3b9) is our shared task tracker.

## Getting started

1. Clone https://github.com/Winathons/roomay and open the repository root (containing `workpeg.json`).
2. Create and activate a virtual environment (on Windows: `py -m venv .venv`, then `.\.venv\Scripts\Activate.ps1`).
3. `python -m pip install -r requirements-dev.txt`
4. `workpeg ui serve ui/` to view the local interface.
5. `workpeg ui build ui/` to verify compilation.
6. Read `AGENTS.md` and [docs/staging.md](docs/staging.md) before starting project work.

## Choose and claim a Linear issue

All feature tasks start unassigned. Before changing code:

1. Choose an unassigned Backlog issue, read the entire description, dependencies and acceptance criteria.
2. Assign the issue **to yourself** and move it to **In Progress**.
3. Coordinate changes to shared Workpeg tables, `workpeg.json`, or common UI components with collaborators.

## Branch strategy

- **main:** shared integration and release-candidate branch; GitHub default branch.
- **WOR-<id>-short-feature:** personal feature branch based on the latest `origin/main`.

```powershell
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c WOR-8-hotel-schema
```

On a first checkout, use `git switch --track origin/main` if the local branch does not exist.

Commit and push only work related to the Linear issue. Open a PR **into main**, with the issue ID in the PR title/body. Do not push directly to main; do not force-push shared branches.

## PR requirements

- Linked issue and a summary of changes.
- Exact verification commands and results (at minimum `python -m compileall -q ui function` and `workpeg ui build ui/` for code changes).
- Screenshots for visible UI changes, and negative-case tests for hotel/auth logic.
- Known limitations and a reviewer before merge. Do not claim locally mocked AI, voice or payment as a live integration.
- **Definition of Done:** acceptance criteria verified, code merged, documentation updated, and no serious known correctness or access-control failure. If GitHub–Linear integration auto-marks an issue Done on merge before acceptance testing, restore the correct issue status.

## Workpeg safety

- Use a dedicated development Workpeg business with fictional hotel records, **not** real production guests.
- `--fake-cloud` uses the actual Workpeg API and is **not** a sandbox. Verify the isolated test business before using it.
- Never commit `WORKPEG_PK`, passwords, API keys, `.env`, actual guest identity documents or live customer data. Never put privileged developer keys in public browser code.
- Prefer native Workpeg UI, business-scoped tables, staff session and role permissions over a second general-purpose backend.
- A booking is not proof of an active stay; room occupancy, cleaning and maintenance are distinct.
- Public guest access, voice calls, PBX and payment integrations must be verified separately before claiming they work.

## Links

- [Project board](https://linear.app/workpeg/project/roomay-workpeg-hospitality-hackathon-7b7a7ce4b3b9)
- [Main-branch and Codex instructions](docs/staging.md)
- [Workpeg SDK](https://developers.workpeg.com/docs/latest/)

