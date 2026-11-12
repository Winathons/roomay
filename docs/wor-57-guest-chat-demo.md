# ROOMAY Local Hotel Journey

This local browser journey shows how the existing guest, Reception and
Housekeeping contracts fit together. Guest classification, clarification,
routing, stay checks and explicit confirmation reuse WOR-18. Request creation,
Reception assignment, Housekeeping acknowledgement, start and resolution use
the canonical service-request domain functions. A small process-memory store
holds the explicitly synthetic request and audit history; it is not an
operational or Workpeg writer.

## Run locally

From the repository root in PowerShell:

```powershell
..\.venv\Scripts\python.exe -m tools.guest_chat_demo
```

Open `http://127.0.0.1:8765/`. Stop the server with `Ctrl+C`. The server binds
only to IPv4 loopback. It makes no outbound requests. If port 8765 is busy, run
with `--port 8766` and open the matching URL.

The interface displays **SYNTHETIC DEMO — NO LIVE HOTEL REQUEST SUBMITTED**.
Start at My Stay, submit and confirm “Please bring extra towels to room 205,”
open Reception and assign the request, then use the Housekeeping tab to
acknowledge, start and resolve it. Return to My Stay to see the same final
status. Reception also shows the Room 205 active stay, rooms board, metrics and
the demo-only request history.

The Guest, Reception and Housekeeping tabs are selectable demo roles. They are
not authenticated identities or proof of real permissions. Each demo session
uses fictional records and one synthetic active stay. Request/status updates
are kept in the server process memory, so they survive normal page reloads for
the same HttpOnly session cookie (up to 20 minutes inactivity). Restarting the
server discards them. No data is seeded to Workpeg or PostgreSQL, and no real
staff are notified.

The optional “Start voice input” control requires browser support for on-device
Web Speech recognition and an already-installed `en-NG` language pack. It does
not enable cloud recognition or download language packs. Type a message if
private on-device recognition is unavailable. See
[WOR-19 browser voice intake](wor-19-browser-voice-intake.md).

Try `Please bring extra towels to room 205.` or `Abeg, my AC no dey cool for
room 205.`. Emergency messages ask the guest to contact Reception; nobody is
contacted by the demo.

## Validation

```powershell
..\.venv\Scripts\python.exe -m unittest tests.test_guest_chat_demo -v
```

The endpoint tests exercise the browser HTTP routes and confirm status changes
survive reloading through the same session. Manual browser review verifies
visible navigation, request controls and responsive screens. None of these
checks prove hosted Workpeg access, staff login, guest verification or live
request persistence. The offline text classifier is not an AI model, and
Pidgin examples do not measure speech-recognition accuracy.

## Production work still required

The production receptionist route remains an authenticated, read-only Workpeg
reader. Before real guest use, Roomay needs the owner-approved trusted guest
verification and active-stay lookup, a server-backed role/department identity
boundary, an approved single source of truth and request/audit writer, verified
department permissions, concurrency control and read-back reconciliation. This
journey calls none of Workpeg, Vapi, YarnGPT or PostgreSQL and does not replace
WOR-61/WOR-62 or Yusuf's WOR-17 guest portal. Never expose its synthetic role
switch or session mechanism as a public endpoint.
