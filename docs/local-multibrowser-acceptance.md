# ROOMAY local multi-browser acceptance

This procedure exercises the existing Guest → Reception → Housekeeping request lifecycle with **fictional data in one local Python process**. It does not contact Workpeg, write hosted rows, or represent authenticated hotel accounts. The local QA role selection is a test harness only.

## Start the local app

Open PowerShell in the feature worktree and run:

```powershell
Set-Location C:\Users\HomePC\Desktop\roomay-workspace\roomay-local-multibrowser-acceptance
..\.venv\Scripts\python.exe -m tools.guest_chat_demo --port 8765 --enable-local-qa
```

Keep that terminal open. The server binds only to `127.0.0.1`. It stores example state in process memory; stopping the process clears the scenario. Do not use `--fake-cloud`, expose this port to the LAN, or tunnel it publicly.

Open `http://127.0.0.1:8765/__qa/` in three separate Chrome profiles (or separate browser profiles that do not share cookies). For example, from another PowerShell window:

```powershell
$Chrome = Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'
if (-not (Test-Path $Chrome)) { $Chrome = Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe' }
Start-Process $Chrome -ArgumentList @("--user-data-dir=$env:TEMP\roomay-guest-profile", 'http://127.0.0.1:8765/__qa/')
Start-Process $Chrome -ArgumentList @("--user-data-dir=$env:TEMP\roomay-reception-profile", 'http://127.0.0.1:8765/__qa/')
Start-Process $Chrome -ArgumentList @("--user-data-dir=$env:TEMP\roomay-housekeeping-profile", 'http://127.0.0.1:8765/__qa/')
```

If Chrome is installed in a nonstandard location, use that executable path. Each profile has its own local session cookie. The scenario join code joins those separate cookies to one short-lived in-memory fixture; it is not an identity credential.

## Acceptance sequence

1. In the first QA profile, click **Create scenario**. Copy the generated scenario code before navigating away.
2. Paste the same code into the Guest profile and choose **Open My Stay**. In the Reception profile, paste it and choose **Open Reception**. In the Housekeeping profile, paste it and choose **Open Housekeeping**. Each selection creates a distinct browser session in the same test scenario.
3. In Guest / My Stay, send `Please bring extra towels to my room.` Review the proposed Housekeeping request and explicitly confirm it. The UI should say it is ready in the example session and has not been sent to hotel staff.
4. In Reception, refresh the page if needed. The request should appear as **Received**. Assign it to Housekeeping.
5. In Housekeeping, refresh if needed. The request should appear as **Assigned**. Advance it through **Acknowledge → Start → Resolve**.
6. In Guest / My Stay, reload. The request should now show **Resolved**. This is shared process-local test state, not durable persistence.
7. Negative checks: Guest cannot assign or resolve; Reception cannot perform Housekeeping transitions; a Guest claim for room 120 is rejected against the trusted synthetic stay; duplicate confirmation of the same proposal creates one request; an expired or invalid scenario code is denied. Automated regression tests cover these paths.

The generated fixture is fictional. Room 205 is the verified room only within this local test scenario. No actual Workpeg account, guest, staff membership, hotel permission, request, notification, or audit record is involved.

## What this establishes

- Independent browser cookies can observe consistent request and status state while the one local process is running.
- The existing domain request lifecycle, confirmation, department assignment and transition checks are reused.
- Role checks are exercised in the local harness, not proven as real authentication.
- State survives page navigation and reload in the same process, but not a server restart.
- Workpeg Tables remain the intended operational source of truth. This QA store is not a competing production writer.

For hosted authorization, use separately provisioned Workpeg Owner/Member accounts and the supported Workpeg application paths. This local role chooser cannot perform that test. Do not change table permissions or use these sessions as evidence of hosted staff access.
