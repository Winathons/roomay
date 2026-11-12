# WOR-25 — Workpeg tester and release handoff

Updated: November 12, 2026. This runbook describes the current Workpeg SDK
0.152.0 development path and the separate, incomplete hosted release path. It
does not publish, install, or write to Workpeg.

## Current product boundary

The approved Peg namespace is `roomay`; the manifest is [workpeg.json](../workpeg.json).
It currently contains the namespace only: there is no Function configured for
the read-only Reception application. The compiler writes local UI assets to
`ui/dist/`.
The compiled production Workpeg router currently exposes exactly:

- `/` — a short Reception availability message.
- `/b/<business_id>/reception` — the authenticated, read-only Reception
  workspace. It discovers and reads the nine canonical hotel/request tables,
  validates the complete snapshot, and then displays Today, Rooms &
  Availability, and Service Requests. It does not create or update records.

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
Set-Location C:\Users\HomePC\Desktop\roomay-workspace\roomay

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
as loaded. It has no guest portal, Housekeeping workspace, QA role switcher,
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
Set-Location C:\Users\HomePC\Desktop\roomay-workspace\roomay
& .\.venv\Scripts\python.exe -m tools.guest_chat_demo --port 8765 --enable-local-qa
```

Open `http://127.0.0.1:8765/__qa/`. This session is local test state; it is not
Workpeg authentication and it does not read or persist hotel records in
Workpeg. Do not present its requests or staff transitions as real operations.
Stop it with Ctrl+C. Keep it separate from the `roomay.dev.workpeg.com` browser
origin and never expose it on the LAN or public internet.

## Offline release checks

From the repository root, using the existing pinned environment:

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

Verified against the installed `workpeg==0.152.0` CLI help and the official
manifest, project, function, CDN, and architecture documentation:

| Step | Supported now | Effect |
| --- | --- | --- |
| Compile the UI | `workpeg ui build ui/` | Creates local `ui/dist/`; no upload or release. |
| Test the development UI | `workpeg ui serve ui/ --fake-cloud` | Local, loopback-only dev origin; authenticates the browser to Workpeg APIs. Not hosted. |
| Prepare project manifest | `workpeg.json` | Keeps existing namespace `roomay`. No identity changes. |
| Upload static CDN assets | `workpeg cdn submit ./ui/dist/` | Requires `WORKPEG_PK` and uploads public static assets. It is not a complete UI/manifest release. Not run. |
| Build/submit a Function | `workpeg function build` / `workpeg function submit <version>` | Available for Function projects; submission requires `WORKPEG_PK`. Function `main` versions have per-version review/approval; Roomay Reception does not invoke a Function. Not run. |
| Submit complete UI + manifest Peg release / create PegStore version | No `workpeg project submit` or UI-release command in SDK 0.152.0 | Official docs list complete project submission/PegStore workflow as not yet available in this CLI. |
| Install for testing | Developer dashboard “Install for testing” (optional, owner/admin action) | The owner reports Roomay is already installed for testing in Roomay AI. This is not a published/reviewed PegStore release. |
| Review/approve/install release | PegStore/dashboard/platform process | Exact complete UI-only release procedure still needs Workpeg confirmation; no release is created by `ui build`, CDN upload, or local dev install. |

Do not upload `ui/dist/` to CDN as a substitute for a reviewed Peg release.
CDN files are public assets. `workpeg.json` identity is `roomay`; never
register a replacement Peg or create another development business. Before a
release, Workpeg must provide the supported UI-only release submission path,
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

## Remaining product blockers

The Workpeg application is an owner-scoped read-only Reception surface. Real
guest identity/session verification, department-level authorization,
request/staff mutations with committed audit, safe concurrency, and a verified
non-owner permission model are not delivered by this UI. The guest and
Housekeeping journeys remain local QA only. Aliameen's WOR-61/WOR-62 source of
truth and Workpeg integration decisions and Yusuf's WOR-17 guest identity
contract must land before those paths can be connected without duplicate
writers or broader table permissions.

