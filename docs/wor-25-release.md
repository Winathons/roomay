# WOR-25 — Workpeg tester and release handoff

Updated: November 14, 2026. This runbook describes the current Workpeg SDK
0.152.0 development path and the separate, incomplete hosted release path. It
does not publish, install, or write to Workpeg.

## Approved MVP and source precedence

The [Roomay project](https://linear.app/workpeg/project/roomay-workpeg-hospitality-hackathon-7b7a7ce4b3b9)
(updated 14 November 2026) and the current brief in
[WOR-25](https://linear.app/workpeg/issue/WOR-25/document-deployment-workpeg-publishing-and-handoff-procedure)
supersede historical staging, SDK 0.149.1 and broad hotel-management instructions.
Use protected `main` and reviewed issue branches. Leave Linear status unchanged
for this documentation task.

The active MVP is verified stay/room-code access through WorkPeg AI, scoped
room guidance, guest complaints/requests committed with audit to WorkPeg Tables,
and receptionist assignment/status updates followed by guest saved-status
readback. Manually initiated progress/feedback email requires a confirmed,
supported capability. WorkPeg Tables remain the sole operational authority.
Booking, check-in/out, standalone Next.js guest-web, voice, WhatsApp and automatic
staff dispatch are deferred. Existing prototypes are not release deliverables.
Shared contracts belong to WOR-77; this runbook neither defines nor changes them.

| Evidence level | What it establishes | What it does not establish |
| --- | --- | --- |
| Offline tests/build | Synthetic policy/controller behavior and compiled artifact safety at a recorded commit | Staff sessions, hosted grants, canonical delivery or live AI |
| Installed Peg readback | Authorized session can read expected fictional canonical rows and refresh | Writes, independent staff access or the guest-to-reception workflow |
| Local `--fake-cloud` | Authenticated local development UI against real APIs, with dev-table isolation | Installed Peg canonical data or a published release |
| Hosted MVP acceptance (WOR-89) | Independently verified guest → WorkPeg AI → canonical request/audit → receptionist update → guest readback | Cannot be replaced by mocks, a local queue, or another database |

## Current product boundary

The approved Peg namespace is `roomay`; the manifest is [workpeg.json](../workpeg.json).
It currently contains the namespace only: there is no Function configured for
the read-only Reception application. The compiler writes local UI assets to
`ui/dist/`.
The compiled production Workpeg router registers `/`, `/b/[business_id]/reception`,
and `/b/[business_id]/reception/[workspace]`. The workspace parameter accepts only
the default view or `housekeeping`; other values fail closed. The supported views are:

- `/` — a short Reception availability message.
- `/b/<business_id>/reception` — the authenticated, read-only Reception
  workspace. It discovers and reads the nine canonical hotel/request tables,
  validates the complete snapshot, and then displays Today, Rooms &
  Availability, and Service Requests. It does not create or update records.
- `/b/<business_id>/reception/housekeeping` — an owner-only, read-only
  Housekeeping preview using the same validated snapshot. It does not establish
  department membership, expose guest names or free-text request descriptions,
  or enable operational actions. All canonical tables remain permission `700`;
  do not share this route with Housekeeping staff as an authorized inbox.

The owner has reported that this route, opened from the installed Peg in the
Roomay AI development business, reads the existing fictional hotel records.
Offline tests and this runbook do not independently re-verify the live service.
Table permissions remain `700`; do not invite a regular staff tester expecting
they can read those rows. A non-owner may receive Access denied. No booking,
check-in, checkout, room assignment, request submission, or department action
is enabled in the Workpeg application.

The separate [local QA journey](../tools/guest_chat_demo.py) offers `/stay`,
`/staff/reception`, `/staff/housekeeping`, and `/__qa/` with synthetic local
session state. It is not a Workpeg route, identity provider, hosted service, or
source of hotel records. The QA role picker is not authentication.

## Launch the real installed Reception app

For a repeat check of the existing Workpeg-hosted test installation, use the
Workpeg account authorized for the **Roomay AI** development business:

1. Sign in to Workpeg using that account and select **Roomay AI**.
2. Open Roomay from the business's installed Apps/Pegs area (the owner reports
   the Peg is installed for testing). Navigate to its Reception page. If
   needed, open the business-scoped path `/b/<verified-business-id>/reception`
   within the Roomay Peg; obtain the business ID from the Workpeg business
   context, not from a guessed URL or another Peg.
3. Confirm the Reception page reaches **Records loaded** and shows the expected
   existing records. Use Refresh to repeat the read. Do not use any developer
   CRUD or setup page, and do not alter records during acceptance.

Access for another person is **not yet verified**. The Workpeg dev-install
guide says a member of the developer business who has the source can run the
dev page on their own computer with their own Workpeg session. The optional
dashboard “Install for testing” step is owner/admin controlled; its presence
does not prove every invited staff member can open the app or read its rows.
The Roomay tables are currently permission `700`, so inviting a regular staff
tester does not grant them row access and they may receive Access denied. Do
not broaden permissions for a demo. If the owner invites a tester, first
confirm business membership and then record the actual access result. The
owner's local server is not remotely accessible to invitees.

## Run the current Workpeg UI build locally

Use Windows PowerShell on the source checkout to compile and run the current
development build under Workpeg's supported dev-install origin. The command
below is supported by the pinned SDK; it does not publish or install a release.
The CLI builds the release-equivalent UI, serves it locally over HTTPS at
`https://roomay.dev.workpeg.com`, and uses the signed-in Workpeg session when
the tester opens the business-scoped page.

Before the first run, install `mkcert` from a trusted package source. If
Chocolatey or Scoop is already installed, Workpeg documents:

```powershell
choco install mkcert
# or: scoop install mkcert
mkcert -version
mkcert -install
```

`mkcert -install` trusts a local development CA on this computer. The first
`--fake-cloud` run also requires an **Administrator PowerShell** to add its
tagged hosts-file entry. Use only the isolated Roomay AI development
business/account. The server accepts requests from this computer only. Port
443 is required; do not pick another port. Check for a listener before starting:

```powershell
Get-NetTCPConnection -LocalPort 443 -State Listen -ErrorAction SilentlyContinue
```

If port 443 is occupied, stop the conflicting local service or postpone the
dev-install check; the Workpeg API rejects alternate ports for this origin.

```powershell
Set-Location 'C:\path\to\roomay' # Replace with your checkout path.

# Confirm this checkout uses the exact repository pin (0.152.0).
& .\.venv\Scripts\python.exe -m pip show workpeg
& .\.venv\Scripts\workpeg.exe --version

# SDK 0.152.0 rejects WORKPEG_BIND_HOST when --fake-cloud is used.
Remove-Item Env:WORKPEG_BIND_HOST -ErrorAction SilentlyContinue

# Run from the project root that contains workpeg.json and ui\main.py.
& .\.venv\Scripts\workpeg.exe ui serve ui/ --fake-cloud
```

Open the exact `https://roomay.dev.workpeg.com/` URL printed by the CLI. Sign
in through Workpeg Accounts with the Roomay AI development account; if sign-in
leaves you on Accounts, reopen the printed URL. Then open
`https://roomay.dev.workpeg.com/b/<verified-roomay-ai-business-id>/reception`
using the business ID from the verified Roomay AI context. Do not paste the ID
into logs, screenshots, or public issue comments.

**Important data boundary:** `--fake-cloud` is a real Workpeg API development
origin, not a mock or offline sandbox. It sends the browser's Workpeg session
to real Workpeg services. Current Workpeg dev-install docs say the dev page's
table data is isolated in a per-business `dv-<uuid>` test namespace, separate
from released Peg data, and may be initialized on first use. Therefore this
local build is for checking authenticated UI/compiler behavior; it is not
evidence that the already installed Peg's canonical `roomay_hotel_v1` and
`roomay_requests_v1` records are being read. If it reports missing tables,
stop and use the installed Workpeg Peg for the owner-verified read check; do not
provision tables or attempt to copy records. The UI code itself calls only
table discovery and row-read helpers; it has no write controls.

`--fake-cloud` uses no `WORKPEG_PK`. Do not set
`WORKPEG_BIND_HOST` (the pinned SDK refuses it in this mode), pass
`--peg-namespace`, or serve from an already-built `dist/`; the namespace comes
from `workpeg.json` and the server enforces the development origin. On Windows,
the CLI maps the dev hostname to loopback. Stop it with Ctrl+C. Cleanup, when
finished, is:

```powershell
& .\.venv\Scripts\workpeg.exe ui dev-clean ui/
```

This removes the SDK-marked hosts entry and that development certificate; the
mkcert root CA remains trusted by Windows unless separately removed.

### Expected screens and truthful failure states

The Workpeg build has Today, Rooms & Availability, and Service Requests inside
the Reception route. It is read-only. It shows explicit loading, empty
inventory, authentication required (401), access denied (403), unavailable,
and complete-records-loaded states. A partial or invalid snapshot is not shown
as loaded. Its Housekeeping preview is owner-only and read-only, not a department inbox.
It has no guest portal, authorized department workflow, QA role switcher,
booking/check-in flow, or real request mutation.

| Observation | Meaning / next check |
| --- | --- |
| Workpeg sign-in or “Authentication required” | Sign in to the authorized Roomay AI account, then reload the exact dev URL. |
| “Access denied” / HTTP 403 | The current account lacks a required table permission or business access. Stop; do not broaden grants as a workaround. |
| Connection unavailable / timeout | Check Workpeg connectivity and the CLI terminal; retry only a read using Refresh. |
| Required table missing/unreadable | The app cannot produce a complete snapshot. In `--fake-cloud`, verify the development-table isolation described above; do not provision from this screen. |
| Records loaded | A read completed for this session. It is not evidence of writes, role authorization for other departments, or production readiness. |

### Separate localhost QA journey

This optional route set is for synthetic workflow rehearsal only. It uses a
separate loopback server and port so it does not collide with the Workpeg
dev-install listener on 443:

```powershell
Set-Location 'C:\path\to\roomay' # Replace with your checkout path.
& .\.venv\Scripts\python.exe -m tools.guest_chat_demo --port 8765 --enable-local-qa
```

Open `http://127.0.0.1:8765/__qa/`. This session is local test state; it is not
Workpeg authentication and it does not read or persist hotel records in
Workpeg. Do not present its requests or staff transitions as real operations.
Stop it with Ctrl+C. Keep it separate from the `roomay.dev.workpeg.com` browser
origin and never expose it on the LAN or public internet.

## Offline release checks

Use the repository root containing `workpeg.json`. Create a private virtual
environment and install the repository pin; never upgrade Workpeg implicitly.
Windows setup: `py -3.13 -m venv .venv`, then
`.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`.
For macOS/Linux:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m compileall -q ui function domain tests
workpeg ui build ui/
workpeg doctor . --offline
python -m unittest tests.test_release_candidate -v
git diff --check
```

Use Node 24 for compiled-controller scenarios. Python 3.13.5 is the previously
verified developer setup; Python 3.12 is used by repository CI and was verified
below. Docker/PostgreSQL integration checks are separate from this minimal
setup; report skipped tests rather than claiming full CI equivalence.

Windows PowerShell, using the pinned environment:

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv\Scripts\python.exe -m compileall -q ui function domain tests
& .\.venv\Scripts\workpeg.exe ui build ui/
& .\.venv\Scripts\workpeg.exe doctor . --offline
& .\.venv\Scripts\python.exe -m unittest tests.test_release_candidate -v
git diff --check
```

These checks use mocked/synthetic fixtures and inspect the compiled artifact;
they do not connect to Workpeg or prove data permissions, installation, or
hosted persistence.

## Workpeg packaging and publishing status

The capability boundary below is pinned to installed `workpeg==0.152.0` CLI
help. Current online documentation describes newer SDK features; it is not a
versioned guarantee for this checkout:

| Step | Supported now | Effect |
| --- | --- | --- |
| Compile the UI | `workpeg ui build ui/` | Creates local `ui/dist/`; no upload or release. |
| Test the development UI | `workpeg ui serve ui/ --fake-cloud` | Local, loopback-only dev origin; authenticates the browser to Workpeg APIs. Not hosted. |
| Prepare project manifest | `workpeg.json` | Keeps existing namespace `roomay`. No identity changes. |
| Upload static CDN assets | `workpeg cdn submit ./ui/dist/` | Requires `WORKPEG_PK` and uploads public static assets. It is not a complete UI/manifest release. Not run. |
| Build/submit a Function | `workpeg function build` / `workpeg function submit <version>` | Available for Function projects; submission requires `WORKPEG_PK`. Function `main` versions have per-version review/approval; Roomay Reception does not invoke a Function. Not run. |
| Submit complete UI + manifest Peg release / create PegStore version | No `workpeg project submit` or UI-release command in SDK 0.152.0 | Installed `project --help` lists only `create`; `ui --help` has no submit command. Current online docs describe a newer whole-project submission workflow, not available in this pin. |
| Install for testing | Developer dashboard “Install for testing” (optional, owner/admin action) | The owner reports Roomay is already installed for testing in Roomay AI. This is not a published/reviewed PegStore release. |
| Review/approve/install release | PegStore/dashboard/platform process | Exact complete UI-only release procedure still needs Workpeg confirmation; no release is created by `ui build`, CDN upload, or local dev install. |

Do not upload `ui/dist/` to CDN as a substitute for a reviewed Peg release.
CDN files are public assets. `workpeg.json` identity is `roomay`; never
register a replacement Peg or create another development business. Before a
release, the owner and Workpeg must confirm a version-compatible UI-only
release submission path,
review steps, version immutability/update procedure, and authorized-business
installation instructions. The owner must approve any token creation, upload,
submission, release, install, permissions change, or hosted data write
separately.

## Owner handoff checklist

- [ ] Confirm the `main` commit under review and SDK pin `0.152.0`.
- [ ] For existing records, open the already installed Peg in Roomay AI and
      run the Reception read-only check using the authorized owner account.
- [ ] Invite a tester to the Roomay AI business only if appropriate; verify
      their actual Workpeg access. Current `700` permissions do not imply
      access for a regular staff member.
- [ ] If the tester needs to validate the local build, provide source/repo
      access and have them run their own local `--fake-cloud` server under
      their own authorized development session. It is not a shared URL.
- [ ] Record only sanitized outcome labels (loaded / 401 / 403 / missing /
      unavailable). Do not share cookies, business IDs publicly, guest rows,
      or screenshots containing personal data.
- [ ] Obtain Workpeg's supported complete UI/manifest Peg release and
      approval/install procedure before any hosted release action.
- [ ] Keep WOR-28, WOR-29, WOR-14, WOR-15, WOR-61 and WOR-62 open until their
      actual access, authorization, persistence, audit, and staff permission
      acceptance is independently met.

## Release gates and deployment approval

All gates apply to the exact candidate commit and artifact; a green build alone
is not release approval.

1. Record the reviewed `main` SHA, SDK/Python/Node versions, build results and
   artifact checksum. Inspect the compiled routes, read-only helper allowlist,
   diagnostic/fixture exclusion and secret scan via the release-candidate tests.
   Do not relax those tests to enable unapproved writes.
2. Check the GitHub `Workpeg UI build` workflow result and reviewer approval.
   Verify current branch-rule enforcement with the repository owner; historical
   observations in [WOR-68](wor-68-ci-enforcement.md) are not current proof.
   This task does not change repository settings.
3. Obtain installed-Peg readback and independent account/permission evidence.
   Record owner, restricted staff, unauthenticated and wrong-business outcomes
   through the supported test process. A missing identity or test mechanism is
   **blocked**, not pass. Keep `700` permissions; do not grant access to pass QA.
4. Before calling this an MVP release, complete WOR-89 with a fictional active
   stay: verified code → correctly scoped facts → guest-confirmed structured
   request → one canonical WorkPeg request plus committed audit → receptionist
   assignment/update → guest reads saved status. Verify retries/duplicates,
   invalid or expired identity, cross-room denial and failure reporting.
   Confirm manually initiated email capability and delivery separately. No
   live tests or writes are authorized by this runbook.
5. Obtain a separate explicit owner approval identifying the candidate SHA,
   artifact checksum, SDK, target business, release version, approved actions,
   operator, acceptance evidence and rollback target. Record it in the release
   record without credentials. Token issuance/use, upload, submission and
   installation each need authorization; this documentation PR grants none.
6. Confirm with Workpeg the supported UI-only packaging/review/install path for
   the pinned SDK, version behavior and supported rollback operation. If an
   upgrade is required, propose and verify it separately. Do not submit the
   dormant Function or use CDN upload as a substitute.

### Secrets and sanitized handoff record

No SDK token is required for offline checks or fake-cloud. Publishing credentials
such as `WORKPEG_PK` are not staff sessions or Tables API credentials. If later
authorized, the owner supplies them through an approved secret store or private
operator environment, never source, browser code, command arguments, screenshots,
logs, chat or PR text. Do not print environment contents or share staff sessions;
each tester uses their own account. If exposure is suspected, stop release,
notify the owner privately and have the owner revoke/rotate the credential before
resuming; never paste the value into the incident record.

Record: candidate SHA and checksum; tool versions; exact command/result and
skips; evidence level; date/operator; fictional scenario; sanitized outcome
(loaded/denied/missing/unavailable); approval reference; rollback target; open
blockers. Keep business/record identifiers, guest details and credentials out of
public evidence. Share access instructions privately, not shared passwords.

## Rollback and failed-release procedure

- **Before upload/install:** stop the release if any gate fails. Retain the
  last accepted installed version. Fix through a new reviewed PR to `main`;
  do not reset protected main or rewrite another developer's work.
- **Local dev server:** stop with Ctrl+C and use `workpeg ui dev-clean ui/`
  for SDK-managed hosts/certificate cleanup. This is local cleanup, not hosted
  rollback or data restoration.
- **After an authorized install fails:** the operator pauses further release
  actions, records sanitized symptoms and the exact version, and notifies the
  owner. The owner must approve the supported platform operation to restore
  the last accepted version. No tested downgrade/reinstall command exists in
  this handoff; obtain Workpeg confirmation before relying on one. If rollback
  is unsupported, keep acceptance blocked and obtain an approved recovery plan.
- Restore only the recorded, previously reviewed artifact/version through that
  confirmed process. Treat immutable versions as immutable; do not overwrite
  them. Reverting Git alone does not revert a hosted Peg. Any source rollback
  uses a reviewed revert PR and a separately approved release.
- After recovery, repeat installed-Peg readback and the relevant permission and
  MVP checks, recording results before resuming. Artifact rollback does not
  roll back tables, permissions or audit. Data recovery/migrations need a
  separate owner-approved plan; never delete or reseed records as rollback.

## Remaining product blockers

Installed readback remains owner-reported, not independently verified here.
Non-owner/department access, verified guest identity, supported AI actions,
idempotent canonical request/audit commits, receptionist mutations and guest
status readback remain hosted acceptance gates (WOR-28/29, WOR-15/17,
WOR-18/64/87, WOR-34, WOR-65/69/77 and WOR-89). Manually initiated email
(WOR-88), complete pinned-SDK release/install approval and a tested platform
rollback path also remain unverified. Local QA and dormant backend/voice code
do not satisfy these gates. Do not reopen deferred booking or guest-web scope.

## SDK evidence and documentation drift

Read on 14 November 2026:

- [Current project guide](https://developers.workpeg.com/docs/latest/projects/)
  now documents `workpeg project submit`, whole-project release metadata and
  newer SDK behavior (including references to 0.161.0). The previous assertion
  that the current official guide has no whole-project path is stale.
- [Manifest guide](https://developers.workpeg.com/docs/latest/manifest/) and
  [Function guide](https://developers.workpeg.com/docs/latest/functions/) describe
  current packaging and token boundaries. Do not transplant newer manifest
  fields or commands into this 0.152.0 candidate without compatibility review.
- Installed 0.152.0 `project --help`, `ui --help`, `ui serve --help`,
  `function --help` and `cdn --help` confirm the command matrix above. These
  were read-only help calls; no token, submission or install was attempted.
- For the Windows JavaScript MIME issue, see the
  [0.152.0 compatibility note](workpeg-sdk-0152-compatibility.md). From the
  repository root the wrapper is
  `.\.venv\Scripts\python.exe tools\workpeg_serve_compat.py ui/ --fake-cloud`.
  Its browser retest remains owner-operated; all real-service restrictions above
  still apply.

## Offline verification record — 14 November 2026

Baseline: protected `origin/main` at
`1545ef91ab1ac83de73cde18bf6997c204dbf249`; clean new checkout and isolated
`WOR-25-release-handoff-docs` branch. Only this Markdown file changed.
Environment: Linux, Python 3.12.14, Node v24.22.1, Workpeg 0.152.0.
Commands ran from the repository root with `.venv/bin` first on `PATH`:

| Exact command | Result |
| --- | --- |
| `python -m venv .venv` | Passed |
| `.venv/bin/python -m pip install -r requirements-dev.txt` | Passed; installed Workpeg 0.152.0 |
| `python -m unittest discover -s tests -v` | 566 tests, OK, 29 skipped (537 passed) |
| `python -m compileall -q ui function domain tests` | Passed |
| `workpeg ui build ui/` | Passed; built `ui/dist` |
| `workpeg doctor . --offline` | No issues; 15 checks, 6 skipped |
| `python -m unittest tests.test_release_candidate -v` | 9 tests passed; fresh temporary compiled artifact checked |
| `git diff --check` | Passed |

The 29 suite skips comprise 24 PostgreSQL backend tests, two PostgreSQL intake
tests (no isolated database configured), two opt-in Docker voice smokes and one
Gunicorn smoke (optional runtime not installed). Those dormant prototype checks
were not enabled for this documentation task. Doctor skips are not hosted proof;
its heuristic labels the directory a Function project despite the UI-only
manifest, so that label is not deployment authorization.

No fake-cloud server, installed-Peg retest, WorkPeg table/permission change,
SDK token issuance, live AI/email service, publishing or hosted rollback was
run. Full GitHub CI and independent hosted MVP acceptance remain separate gates.
