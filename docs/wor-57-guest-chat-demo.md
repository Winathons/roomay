# Local hotel journey — internal QA instructions

This loopback-only browser harness uses Roomay's existing conversation-intake,
hotel projection and service-request transition contracts. It is not a customer
portal and is not registered in the Workpeg Peg UI. `The Linden House` and its
named guests are invented example records.

## Start the local journey

From the repository root in PowerShell, using the pinned environment:

```powershell
..\.venv\Scripts\python.exe -m tools.guest_chat_demo --port 8765 --enable-local-qa
```

The three workspaces are separate routes:

- `http://127.0.0.1:8765/stay`
- `http://127.0.0.1:8765/staff/reception`
- `http://127.0.0.1:8765/staff/housekeeping`

To select a test role, visit `http://127.0.0.1:8765/__qa/`. This internal
loopback-only page requires the explicit `--enable-local-qa` flag. It creates a
test session and chooses an example role; it does not authenticate a user,
verify Workpeg membership, or prove hotel permissions. The customer/staff pages
have no role switcher or links to another role's workspace. Server-side session
role checks guard each staff route and action. Without the flag, `/__qa/` and
its role-selection endpoint are unavailable.

## Example journey

1. Choose **My Stay** in the internal QA page.
2. Submit `Please bring extra towels to room 205.` and confirm the reviewed
   Housekeeping request.
3. Choose **Reception**, review today's example metrics and room overview, and
   assign the request to Housekeeping.
4. Choose **Housekeeping** and acknowledge, start and complete the assigned
   task.
5. Return to **My Stay** and confirm the request status reflects the changes.

Guest API responses contain only the example guest's stay and own request
projection. Reception receives the example hotel overview. Housekeeping
receives only work assigned to its department; guest identities and hotel-wide
metrics are omitted. Data in each response is built from synthetic in-process
records and canonical domain rules. It is not Workpeg or PostgreSQL data.

## State, contact and safety limits

The local process holds request and example audit state in memory. It survives
refresh for the same HttpOnly session cookie (up to 20 minutes idle), but it is
lost when the server stops. UI notices describe this as an example property and
state that updates are not sent to hotel systems. The assistant never claims a
hotel team was contacted. No real Reception phone or emergency number is
configured; the guest page points to the hotel's official contact information
and local emergency services without inventing a number.

The optional voice control uses only on-device Web Speech recognition when
the browser confirms an already-installed en-NG pack. It does not enable cloud
recognition, download a language pack, or store raw audio. Typed input remains
available. Text classification is the existing deterministic WOR-18 intake
contract, not a live AI service.

No Workpeg API, PostgreSQL, Vapi or YarnGPT connection is made by this harness.
No booking, check-in, check-out or guest service request is persisted to a
hotel system. Do not expose this server beyond loopback.

## Validation

```powershell
..\.venv\Scripts\python.exe -m unittest tests.test_guest_chat_demo tests.test_guest_voice_intake -v
```

The tests exercise browser HTTP routes, role-scoped response shapes, route and
action denial, confirmation, all request transitions, replay behavior, reload
within a session, privacy filtering, and local voice-control behavior. Manual
browser testing is still required for rendered layout at desktop and mobile
sizes. The real guest identity/session path, Workpeg read/write authorization,
durable request/audit writer and staff permissions remain blocked on WOR-17,
WOR-61 and WOR-62.
