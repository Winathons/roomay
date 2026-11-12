# Roomay — Instructions for human contributors and Codex

## Product and source of truth
- **Roomay is a real Workpeg-native hotel operations product.** The November 13–14, 2026 Workpeg Hospitality Hackathon is a development milestone, not an excuse to substitute nonfunctional screens for a working system.
- Product requirements are genuine Workpeg-persisted room inventory, bookings, stays, service requests, multi-role staff operations and verified guest channels. A passing compile or synthetic UI is not a completed product.
- [Linear Roomay project](https://linear.app/workpeg/project/roomay-workpeg-hospitality-hackathon-7b7a7ce4b3b9) owns requirements, issues, acceptance criteria and progress.
- [Official Workpeg SDK documentation](https://developers.workpeg.com/docs/latest/) is authoritative for platform APIs. Inspect installed SDK `0.152.0` and documentation before using widgets, table helpers, functions, schemas, or CLI commands. **Do not invent Workpeg APIs.**
- Read `README.md`, `CONTRIBUTING.md`, `docs/staging.md`, and relevant Linear issue before modifying code.

## Git workflow
- The shared integration branch is now **`main`**. The former `staging` branch was removed after the WOR-68 migration.
- Feature branches start from the latest `origin/main`, named `WOR-<number>-short-feature`; all new PRs target **`main`**.
- Do not commit directly to `main`, force push, amend other people's commits, merge PRs, change repository settings or delete branches unless the user explicitly authorizes the action.
- Team issues start unassigned. A developer claims the Linear issue and sets In Progress before making code changes. Do not claim a teammate's work automatically.
- Keep changes limited to the issue's acceptance criteria; stop and document uncertainty instead of guessing platform behavior.

## Workpeg-first architecture
- The staff UI is a Workpeg **Python Peg UI** compiled by the SDK, not a new standalone React backend.
- Primary operational data belongs to **Workpeg business-scoped tables**, with Workpeg authenticated staff sessions and role permissions.
- Prefer native `workpeg.*` UI helpers and manifest-declared AI table actions over custom functions. Add backend code only when the supported platform cannot meet a verified requirement.
- Do not assume `localhost:8081` establishes Workpeg authentication or remote data persistence. **WOR-28** verifies actual table create/read/update across refresh in the isolated development business before WOR-29 and WOR-34 integrate live hotel workflows. Workpeg developers confirmed staff-session Peg UI helpers can run locally with `--fake-cloud` without a published release; Functions/custom save hooks have different deployment requirements.
- No production customer data during engineering. `--fake-cloud` uses a real Workpeg origin and APIs: use only the isolated Roomay AI development business. With SDK 0.152.0 it binds to loopback itself and refuses whenever `WORKPEG_BIND_HOST` is set; do not set that variable, change its port from 443, or pass `--peg-namespace`. A locally trusted mkcert certificate and (on Windows) an Administrator terminal for the hosts-file edit may be needed. The current SDK also isolates dev-page tables under a per-business `dv-*` test namespace; see `docs/wor-25-release.md` before launch.
- **Temporary synthetic fixtures are test-only.** Do not pass fictional hotel data off as operational records, and do not ship `/demo/reception` or the `/b/[business_id]/dev-smoke` diagnostic route in a hotel release. The product receptionist UI must read actual Workpeg rows; track the transition in WOR-34 and release gate WOR-33.
- No Workpeg developer/admin keys in Git, browser JavaScript, screenshots, logs, PRs or public guest-facing code.
- Public guest access, browser voice, WhatsApp and PBX/telephony are real product requirements requiring supported APIs, authenticated access, observability and end-to-end verification. Until implemented, do not display them as functioning or claim real payments/calls/AI inference.

## Hotel invariants
- **Reservation != stay:** A booking/request does not mean a guest checked in.
- Track occupancy, housekeeping readiness and maintenance blocks separately.
- Check-in requires a legitimate, authorized and eligible room. Cancelled, dirty, currently occupied, or blocked rooms must not be assigned incorrectly.
- Reservation-date overlap and concurrent confirmations need verified coordination; if no atomic inventory primitive exists, use explicit **Pending Confirmation** with staff approval rather than promising instant booking.
- Guest/room identity can be inferred from a verified stay but not from caller ID or QR alone. A guest may not access another guest's details.
- Human operators approve sensitive actions such as check-in/out, room changes, room-safety decisions, refunds and guest-record disclosure. Validate all AI outputs.

## Build and verification
Run from the Git repository root, where `workpeg.json` lives:

```bash
python -m pip install -r requirements-dev.txt
python -m compileall -q ui function
workpeg ui build ui/
```

On developer machines also use `workpeg doctor . --offline` (CI may not have Docker), and `workpeg ui serve ui/` to inspect the UI.

- Never hide build failures or claim tests were run when they weren't.
- Add unit tests and negative cases for new logic; prefer deterministic synthetic fixtures and mocked network responses in CI.
- No network calls to real Workpeg tables, paid AI APIs, or live guest/customer endpoints from GitHub Actions.
- PR descriptions must include issue ID, exact commands and results, screenshots for UI changes, security impacts and known limitations. Mark Linear Done only after acceptance criteria are demonstrated and code merged.

