# WOR-57 Offline Guest Chat Demo

This is an isolated, local-only chat preview that delegates classification,
clarification, routing, authorization checks, and request preparation to the
existing WOR-18 conversation-intake contract. It does not add a production
Workpeg route or a second hotel database.

## Run locally

From the repository root in PowerShell:

```powershell
..\.venv\Scripts\python.exe -m tools.guest_chat_demo
```

Open `http://127.0.0.1:8765/`. Stop the server with `Ctrl+C`. The server binds
only to IPv4 loopback. It uses Python's standard library and the repository's
installed dependencies; it makes no outbound requests. If the default port is
busy, pass `--port 8766` and open the matching URL.

The page is explicitly labelled **OFFLINE DEMO — SYNTHETIC DATA — NO REQUEST
SUBMITTED**. Each in-memory session gets a fictional guest context and a
synthetic room 205 scope. The page also tells the guest that this is fictional
and not a real authenticated stay. A room number supplied in chat is never
treated as proof of identity or access.

Try these messages:

- `Hi` (greeting, no room or ticket requested)
- `205` then `Hi are you here` then `The AC is not cooling` (room context is preserved, greeting is not a ticket)
- `Abeg, my AC no dey cool for room 205.`
- `The air conditioner in room 205 is not cooling.`
- `Please bring extra towels to room 205.`
- `I need help with my room.` (clarification / human triage)
- `There is a fire in the room.` (urgent human handoff)

For a prepared request, review the summary and explicitly confirm. Confirmation
only creates a request plan in process memory and the response says it was not
sent or saved; no ticket number or staff notification is produced. Sessions
expire after 20 minutes of inactivity, have a bounded process-local capacity,
and disappear when the server stops. No chat body or cookie is written to
server request logs.

## Validation

Run the dedicated tests with:

```powershell
..\.venv\Scripts\python.exe -m unittest tests.test_guest_chat_demo -v
```

The HTTP tests exercise the handler in memory; they do not claim to be a browser
or hosted Workpeg test. The offline text classifier is not an AI model, and the
Pidgin examples do not measure speech recognition. No screenshot is included
because this environment has no enabled local browser preview surface.

## Production integration still required

Before using this flow with guests, the team must provide a trusted guest
authentication gateway and derive the hotel, active stay, room, and business
scope from trusted Workpeg records. The browser must not supply those claims.
The prepared request then needs a server-side Workpeg persistence path with
verified authorization, idempotency, concurrency control, and read-back
reconciliation, followed by a staff department inbox and guest status tracking.
Those hosted persistence and permission requirements remain blocked pending
Workpeg access verification. Real AI classification and Vapi tool adapters
must feed the same validated domain contract; this demo calls neither AI nor
Vapi. Do not expose the local synthetic-session mechanism as a public endpoint.
