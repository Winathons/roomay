# Roomay

Roomay is a Workpeg-native hotel operations product for Reception, room
inventory, stays, housekeeping, maintenance and guest service. The repository
uses the Workpeg Python UI SDK, pinned to `workpeg==0.152.0`.

**Current verified boundary (November 12, 2026):** The owner reports that the
approved `roomay` Peg is installed for testing in the isolated Roomay AI
development business and its read-only Reception route has loaded the existing
fictional hotel records. The tables remain owner-only (`700`). The Workpeg UI
does not yet offer booking, check-in/out, room assignment or service-request
writes; guest authentication and department permissions are not complete. This
does not represent a published production release.

## Workspaces

The compiled Workpeg release router registers only:

- `/` — Reception availability message.
- `/b/<business_id>/reception` — authenticated, read-only Reception UI with
  Today, Rooms & Availability, and Service Requests views.

The isolated localhost QA journey in `tools/guest_chat_demo.py` has
`/__qa/`, `/stay`, `/staff/reception`, and `/staff/housekeeping` using synthetic
test-session state. It is not a Workpeg route or login, does not read/write
Workpeg records, and must not be presented as a real guest/staff operation.
The detailed launch, access and release instructions are in
[docs/wor-25-release.md](docs/wor-25-release.md).

## First-time local setup

Requirements: Git, Python 3.13.5, Node.js 24 for compiled UI scenarios, and
Windows PowerShell or a POSIX terminal. Workpeg business access is not needed
for offline tests/builds.

### Windows PowerShell

```powershell
git clone https://github.com/Winathons/roomay.git
Set-Location roomay
git fetch origin
git switch main
git pull --ff-only origin main
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

### macOS / Linux

```bash
git clone https://github.com/Winathons/roomay.git
cd roomay
git fetch origin
git switch main
git pull --ff-only origin main
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

The shared integration branch is `main`; `staging` was removed after the
WOR-68 migration. For contribution and branch rules, see
[CONTRIBUTING.md](CONTRIBUTING.md) and [docs/staging.md](docs/staging.md).

## Compile and run locally

From the project root (the folder containing `workpeg.json`):

```powershell
.\.venv\Scripts\workpeg.exe ui build ui/
.\.venv\Scripts\workpeg.exe ui serve ui/
```

Plain `ui serve` is a localhost compiler preview; it has no Workpeg business
session and cannot load hotel rows. To inspect the authenticated Workpeg UI,
open the already installed Peg in the Roomay AI business. For the SDK's local
development origin (`--fake-cloud`), exact PowerShell setup, account/permission
requirements and its real API/test-table behavior, follow the owner-reviewed
[WOR-25 tester handoff](docs/wor-25-release.md). `--fake-cloud` is not a sandbox
and is not the same as the installed Peg's data environment.

The synthetic QA workspace runs separately on a loopback-only HTTP port:

```powershell
.\.venv\Scripts\python.exe -m tools.guest_chat_demo --port 8765 --enable-local-qa
```

Open `http://127.0.0.1:8765/__qa/`. Stop either process with Ctrl+C. The QA
journey is not production authentication or Workpeg persistence.

## Offline verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q ui function domain tests
.\.venv\Scripts\workpeg.exe ui build ui/
.\.venv\Scripts\workpeg.exe doctor . --offline
.\.venv\Scripts\python.exe -m unittest tests.test_release_candidate -v
git diff --check
```

Test totals vary by commit. Tests use synthetic fixtures and mocked Workpeg
responses; passing them does not make a hosted request or prove live permissions
or persistence.

## Security and live data

- Use only the Roomay AI development business for authorized live reads and
  fictional records. Never test on customer records.
- Do not broaden `700` permissions for a tester; a non-owner account may be
  denied even when it can open the app.
- Never place `WORKPEG_PK`, session cookies or credentials in source, browser
  assets, Git, screenshots, logs or issue comments. `WORKPEG_PK` is not a
  browser session credential.
- The Reception app is read-only. No local QA transition is a real booking,
  submitted request, staff notification or persisted audit event.
- Do not publish a Peg, upload assets, install releases, modify hosted data,
  or enable production operations without separate owner authorization and
  passing product/security acceptance.

## Project map

```text
workpeg.json             Approved Peg namespace and manifest
ui/main.py               Production Workpeg routes
ui/hotel_data.py         Authenticated read-only Reception application
domain/                  Hotel, authorization, request and adapter contracts
tools/guest_chat_demo.py Isolated synthetic localhost QA journey
voice_adapter/           Isolated voice services; see their own setup docs
docs/wor-25-release.md   Tester access and Workpeg release handoff
```

Read [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md), and the
[main-branch workflow](docs/staging.md) before project changes.

