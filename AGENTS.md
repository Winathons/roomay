# Roomay — Instructions for human contributors and Codex

## Product and source of truth
- Roomay is a **Workpeg-native hotel operations and guest experience** prototype for the November 13–14, 2026 Workpeg Hospitality Hackathon.
- [Linear Roomay project](https://linear.app/workpeg/project/roomay-workpeg-hospitality-hackathon-7b7a7ce4b3b9) owns requirements, issues, acceptance criteria and progress.
- [Official Workpeg SDK documentation](https://developers.workpeg.com/docs/latest/) is authoritative for platform APIs. Inspect installed SDK `0.149.1` and documentation before using widgets, table helpers, functions, schemas, or CLI commands. **Do not invent Workpeg APIs.**
- Read `README.md`, `CONTRIBUTING.md`, `docs/staging.md`, and relevant Linear issue before modifying code.

## Git workflow
- Default/stable branch: `main`. Shared integration branch: **`staging`**.
- Feature branch from up-to-date `staging`: `WOR-<number>-short-feature`.
- All new feature PRs target **`staging`**, not `main`. Promote staging to main only through a deliberately reviewed release PR.
- Do not commit directly to `main` or `staging`, force push, amend other people's commits, merge PRs, change repository settings or delete branches unless the user explicitly authorizes the action.
- Team issues start unassigned. A developer claims the Linear issue and sets In Progress before making code changes. Do not claim a teammate's work automatically.
- Keep changes limited to the issue's acceptance criteria; stop and document uncertainty instead of guessing platform behavior.

## Workpeg-first architecture
- The staff UI is a Workpeg **Python Peg UI** compiled by the SDK, not a new standalone React backend.
- Primary operational data belongs to **Workpeg business-scoped tables**, with Workpeg authenticated staff sessions and role permissions.
- Prefer native `workpeg.*` UI helpers and manifest-declared AI table actions over custom functions. Add backend code only when the supported platform cannot meet a verified requirement.
- Do not assume `localhost:8081` establishes Workpeg authentication or remote data persistence. **WOR-6** remains a gate until a fictional table row is created/read/updated across reload in a dedicated development business.
- No production customer data. `--fake-cloud` uses a real Workpeg origin and real service APIs: do not invoke it without explicit confirmation of isolated test-business context.
- No Workpeg developer/admin keys in Git, browser JavaScript, screenshots, logs, PRs or public guest-facing code.
- Public guest access and PBX/telephony are not established by the scaffold. Prototype voice with a typed fallback. Do not claim paid AI inference, payments or real telephony without real verification.

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
