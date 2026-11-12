# Roomay

**Roomay is a real hotel operations product** built on the **Workpeg SDK**. It is designed for actual receptionist, reservations, occupancy, housekeeping, maintenance and guest-service workflows, not for displaying fictional operations as a finished application. It aims to connect reception, walk-in bookings, room inventory, actual guest check-ins, housekeeping, maintenance and service requests in one clear staff experience. Future guest channels include a mobile portal, text/voice and WhatsApp.

**Repository:** [Winathons/roomay](https://github.com/Winathons/roomay) · **Work board:** [Roomay in Linear](https://linear.app/workpeg/project/roomay-workpeg-hospitality-hackathon-7b7a7ce4b3b9) · **SDK:** [Workpeg documentation](https://developers.workpeg.com/docs/latest/)

> **Project status (November 9, 2026):** The owner reports authenticated development access and persistence verification for the existing owner-only `roomay_hotel_v1/room_types` table: table creation, direct GET/listing, fictional row create/update/read-back, and persistence after independent browser reload. This does not verify the remaining eight tables, staff-role permissions, production persistence, or a published Peg release. Do not modify or recreate the existing `room_types` table or its fictional record.

## Start here — first-time team setup

**You'll need:**
- **Git** and access to the [Roomay GitHub repository](https://github.com/Winathons/roomay).
- **Python 3.10 or newer**. The development setup uses Python **3.13.5** with `workpeg==0.152.0`.
- A terminal (Windows PowerShell, macOS Terminal or Linux shell) and an editor such as VS Code.
- Internet access to clone and install packages the first time.

**Node 24 is required for the compiled UI offline tests.** No Docker, Supabase,
Firebase, Workpeg API token or separate database is needed for local UI/testing.
Workpeg account access becomes important later for authenticated business records.

The release router exposes the read-only receptionist application at
`/b/<business_id>/reception`. It reads the nine-table
[hotel integration contract](docs/workpeg-integration.md), never provisions or
seeds records, and enables no booking, check-in, assignment, or request writes.
The former demo, diagnostic smoke, and raw adapter routes are not registered in
the release router. Their source remains isolated for offline contract testing.
See [WOR-34 implementation notes](docs/wor-34.md). Authenticated development
`room_types` persistence is owner-reported verified; multi-table provisioning,
role permissions and production integration remain unverified.

### Step 1 — Clone the existing repository

**Windows PowerShell**

```powershell
git clone https://github.com/Winathons/roomay.git
cd roomay
git fetch origin
git switch --track origin/staging
```

**macOS / Linux**

```bash
git clone https://github.com/Winathons/roomay.git
cd roomay
git fetch origin
git switch --track origin/staging
```

`main` is the stable branch; **`staging` is where the latest team development and offline hotel model live**. If you already have a local `staging` branch, run `git switch staging` and `git pull --ff-only origin staging` instead.

> **Important:** You have cloned Roomay already. **Do not run `workpeg project create roomay` again** or put another `roomay/` folder inside the repo. Run all commands below from the directory with `workpeg.json`, `ui/` and `requirements-dev.txt`.

### Step 2 — Create a private Python environment

**Windows PowerShell**

```powershell
py --version
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

If `py` is not recognized, try `python --version` and `python -m venv .venv`. A successful activation usually shows `(.venv)` before your terminal prompt.

**macOS / Linux**

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

The repository pins Workpeg in `requirements-dev.txt` (currently **`workpeg==0.152.0`**). Please **do not casually upgrade** the SDK; Workpeg is pre-1.0 and changes may break the Python UI compiler. The `.venv/` directory is Git-ignored.

### Step 3 — Run Roomay locally

With your virtual environment active, **from the repo root**:

```powershell
workpeg ui serve ui/
```

Open the **local address printed in your terminal** (the original scaffold used `http://localhost:8081/`, but the port may differ). The current starter interface may still show **“Hello from roomay”** while the real receptionist UI is being developed.

Leave the terminal open while you use the browser. `Ctrl+C` stops the server. Edits to supported UI Python files usually trigger a rebuild and browser refresh. The receptionist route has an offline-verified Workpeg transport, and the owner reports successful authenticated table discovery; a successful build or table listing is not proof of persistent hotel records.

### Step 4 — Run the offline tests and build

Open **another terminal**, return to the repository root and activate the same virtual environment (or stop the UI server first).

```powershell
python -m unittest discover -s tests -v
python -m compileall -q ui function domain tests
workpeg ui build ui/
workpeg doctor . --offline
```

**Expected on the November 6 staging snapshot:**
- Unit tests: **84 passing**, including compiled UI tests with mocked
  persistence, authorization, empty, error, and receptionist states;
  the command ends in `OK`.
- Syntax compilation: no output when successful.
- Workpeg UI build: `Built to ui/dist` (or `ui\dist` on Windows).
- Doctor: no issues on the original Windows developer's setup; it may skip optional checks on machines without Node.js or Docker.

The unit tests exercise **pure Python hotel rules** and the compiled development
screen with mocked Workpeg responses. They use **fictional fixtures** and **do not
connect to Workpeg's live database**.

The UI build checks that the Workpeg Python interface compiles to browser assets; it does **not** test remote records or prove the offline Python hotel rules are already called by the browser.

### Step 5 — Understand the project folders

```text
roomay/
├── workpeg.json            # Peg namespace and manifest
├── ui/
│   ├── main.py             # Workpeg route registration
│   └── hotel_data.py       # Authenticated read-only receptionist application
├── function/               # Optional Python hook/function runtime
├── domain/
│   ├── schema.py           # Proposed Workpeg hotel table schema
│   ├── hotel.py            # Pure availability/eligibility and validation rules
│   ├── fixtures.py         # Synthetic rooms, guests, stays and bookings
│   ├── reception.py        # Canonical read-only receptionist projection
│   └── reception_demo.py   # Legacy synthetic projection used only in tests
├── tests/
│   └── test_hotel.py       # Offline hotel regression tests
├── docs/
│   ├── hotel-model.md      # Domain assumptions, limitations and next steps
│   ├── reception-demo.md   # WOR-32 UI behavior, screenshots and limits
│   ├── workpeg-capabilities.md # Workpeg integration readiness
│   └── staging.md          # Branches, CI and Codex workflow
├── AGENTS.md               # Instructions for Codex and contributors
├── CONTRIBUTING.md         # Team collaboration and review rules
└── requirements-dev.txt    # Pinned development SDK
```

The `ui/dist/` compiler output and `.venv/` environment are **generated locally** and are not committed. `function/` exists because the Workpeg scaffold generated it; we do not need to run or publish functions merely to serve the starter UI.

## WOR-23 — Synthetic acceptance rehearsal (not hosted E2E)

To rehearse the complete booking → check-in → guest AC request → maintenance
update → blocked-room refusal → alternative → checkout planning flow on
fictional in-memory data, run:

```powershell
python -m unittest discover -s tests -p test_wor23_acceptance.py -v
```

See [WOR-23 acceptance walkthrough](docs/wor-23-synthetic-acceptance.md)
for the exact scenario, authorization/negative cases, evidence labels,
and the separate **owner-led Workpeg live verification** required before
the product can claim an end-to-end workflow. Passing the test does not save
hotel data or establish guest/department access in Workpeg.

## Making changes with the team

1. Open the [Roomay Linear backlog](https://linear.app/workpeg/project/roomay-workpeg-hospitality-hackathon-7b7a7ce4b3b9), read the issue's dependencies and acceptance criteria, and **assign yourself** an available task.
2. Move it to **In Progress**. Coordinate with teammates if you'll modify shared schemas or the manifest.
3. Update your staging branch and start a feature branch:

   ```powershell
   git status
   git fetch origin
   git switch staging
   git pull --ff-only origin staging
   git switch -c WOR-31-example-feature
   ```

   Replace `WOR-31-example-feature` with your actual issue number and branch name. **Never commit directly to `main` or `staging`.**

4. Implement and verify your changes. Use the offline tests, syntax and Workpeg build commands in Step 4.
5. Commit and push your feature branch; open a GitHub pull request targeting **`staging`**, mentioning its Linear issue ID, tests, screenshots and limitations. Request review.
6. After review and merge, confirm acceptance criteria before marking the issue **Done**. The GitHub–Linear integration may automatically change status on merge even when some work remains; correct the status if necessary.

For a full guide, read [CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md) and [docs/staging.md](docs/staging.md). After integration testing, a **separate reviewed PR from staging to main** is used for a stable release.

## Workpeg account access and security

- **Local UI and tests:** No Workpeg developer token required.
- **Workpeg business-backed engineering:** Must use the confirmed **Roomay AI development business**, an authorized staff session and **fictional test** hotel records. Contact the project lead for legitimate access. Do **not** create another Peg or a real-hotel business independently.
- **Developer API/publishing token (`WORKPEG_PK`):** The Roomay Peg has been approved, so an authorized owner can generate a token when needed for approved publishing or server-side operations. **Never put it in source files, the frontend, GitHub, Linear comments, screenshots or Discord.**
- **`--fake-cloud` is NOT an offline sandbox.** The SDK warns it sends your Workpeg session and writes to the actual service; it also modifies local host/TLS configuration and can expose the server to your network. **Do not run it as part of basic setup.** Get explicit approval and verify the isolated business first.
- **Guest privacy:** Do not enter real hotel guests, government IDs, card information or customer messages into synthetic tests.
- **Capabilities are staged:** Peg approval does not mean publication, installation or that booking/AI/WhatsApp/telephony flows already work.

Current real-backend steps are tracked in [WOR-27 — Peg onboarding](https://linear.app/workpeg/issue/WOR-27), [WOR-28 — authenticated Workpeg table test](https://linear.app/workpeg/issue/WOR-28) and [WOR-29 — hotel schema integration](https://linear.app/workpeg/issue/WOR-29).

## Troubleshooting

| Problem | What to do |
| --- | --- |
| `workpeg ui build ui/` says `'ui' does not exist` | Run `pwd` or `Get-Location`; `cd` to **roomay/**, the folder containing `workpeg.json`. |
| Windows says script execution is disabled when activating `.venv` | In the **current** PowerShell session only, use `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`, then reactivate. If device policy prevents this, use `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` and `.\.venv\Scripts\workpeg.exe ui serve ui/` directly. |
| `py`, `python` or `git` is not found | Install Python/Git, then restart your terminal. Check `py --version`, `python --version` and `git --version`. |
| `workpeg` is not recognized | Activate the correct environment, reinstall with `python -m pip install -r requirements-dev.txt`, and try `python -m pip show workpeg`. |
| Local browser page is empty or outdated | Check terminal compiler errors; save `ui/main.py` and refresh. Use `workpeg doctor . --offline` when needed. |
| The printed local port is already in use | Let Workpeg choose a free port, or try `workpeg ui serve ui/ --port 8082`. Open the **printed URL**, not always port 8081. |
| Tests pass but no bookings appear in Workpeg | Normal for the current offline stage. The domain model is not connected to hosted tables yet. See WOR-28 and WOR-29. |
| Git says `staging` does not exist locally | `git fetch origin` then `git switch --track origin/staging`. |
| GitHub denies `clone` or `push` | Ask the repository owner for collaborator access; authenticate using a supported GitHub credential method. Do not share passwords or tokens in chat. |
| Scaffold README elsewhere says `workpeg run` | Ignore it: the official Workpeg Projects guide says that command is outdated. UI commands above are the tested path. |

## More documentation

- [Workpeg SDK — Getting Started](https://developers.workpeg.com/docs/latest/getting-started/)
- [Workpeg SDK — Projects](https://developers.workpeg.com/docs/latest/projects/)
- [Workpeg SDK — Tables & Rows](https://developers.workpeg.com/docs/latest/tables/)
- [Workpeg SDK — Functions](https://developers.workpeg.com/docs/latest/functions/)
- [Hotel model and invariants](docs/hotel-model.md)
- [Workpeg hotel integration contract](docs/workpeg-integration.md)
- [Service-request lifecycle and persistence contract](docs/service-requests.md)
- [Workpeg integration readiness](docs/workpeg-capabilities.md)
- [UI-only release candidate and owner handoff](docs/wor-25-release.md)
- [Team staging workflow](docs/staging.md)

**The goal for every teammate's first local run:** open Roomay in a browser, run the offline tests, compile the UI, and know exactly which Linear issue to claim next.
