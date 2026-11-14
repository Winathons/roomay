# WOR-87 — Workpeg AI routing and guest-action boundary

## What is implemented offline

Roomay reuses `domain/conversation_intake.py` and the canonical
`CATEGORY_DEPARTMENTS` / `route_category()` map in
`domain/service_requests.py`. The deterministic intake now covers the MVP
examples for extra towels (Housekeeping), air conditioning and socket faults
(Maintenance), food orders (Food & Beverage), and billing questions
(Reception). Requests that do not identify a supported service remain in
clarification or Reception triage. Hazardous electrical wording is handed off
with safety guidance; the response does not claim Reception or emergency
services were contacted.

This is conservative deterministic classification for supported phrase
patterns, including electrical hazard cues such as a buzzing, hot,
burnt-smelling, or sparking socket. It is not broad natural-language
understanding. Wider coverage needs a separately verified AI integration
whose structured proposals remain subject to the same domain and safety
policies.

A structured classifier may not choose a department: the domain recomputes it
from the canonical catalog and rejects a model category when the deterministic
classifier has no matching supported signal. The original guest wording remains
the request description. The existing `GuestActionGateway` binds a pending
proposal to a server-held session and a confirmation handle; cancellation
invalidates it. Confirmation prepares the canonical request/audit plan only.
The plan reports `persisted=False` and `submitted=False`; its proposed
`received` status is not a saved Workpeg row, staff receipt, assignment, or
notification. `assigned_staff_id` remains empty until a trusted staff action.

## Workpeg AI is not connected to these operations

`workpeg.json` intentionally remains `{"namespace":"roomay"}` and declares
no actions. `/b/<business>/chats/new` is Workpeg's built-in AI chat surface,
not a Roomay-specific tool. No Roomay custom action has been discovered or
invoked in Workpeg AI, and the current application does not pass private guest
records or unverified hotel facts into that surface.

The current Workpeg manifest documentation describes two relevant mechanisms:

- Declarative table operations run as the person asking, through that person's
  table permissions. They cannot enforce Roomay's verified active-stay scope
  or request-plus-audit reconciliation over the owner-only canonical tables.
- A manifest phase action can call a Peg Function with platform context. The
  current development-install documentation says phase actions and real-token
  agent calls are not available in that runner. A local `workpeg function test`
  uses a non-authorizing test token and is not evidence of a hosted invocation.

Therefore no action has been added to the manifest and no Function, table,
permission, hosted record, or CDN artifact has been changed. Before a real
action is enabled, the owner and Workpeg must approve and verify the exact
development-business invocation path, actor/stay authorization, source-backed
fact scope, canonical writer, request/audit serialization and reconciliation,
and department readback. The existing native writer remains disabled and is
not wired into the guest interface.

## MVP status semantics

Automatic department routing means the validated request proposal carries the
canonical department. It does not select a named employee or assert that a
department queue has received the request. Routine requests do not require a
Reception classification step in this contract, but they still require guest
confirmation. A hazardous, unclear, unauthorized, stale, or unavailable case
fails closed or hands off; it must not be described as successfully delivered.
Guest status must later be read from committed Workpeg request and audit rows
using the guest's current authorized stay scope. Until then, a live status is
unavailable.

The local QA process-memory journey remains separate from this native Workpeg
integration. It is not a second operational store and is not proof of
Workpeg persistence.

## Deferred Workpeg Peg integrations

Potential later integrations include Email for guest progress messages,
Contacts for authorized hotel contact lookup, Forms for guest feedback, Drive
and Files for approved hotel instructions, Automation for reminders or
unresolved-request follow-up, and Phone for supported hotel contact workflows.
These are possibilities only; none is part of the current ROOMAY capabilities
or a prerequisite for the core request-routing work.

## Verification

The deterministic regressions are in `tests/test_conversation_intake.py`.
They verify canonical department routing, no staff assignment from routing,
explicit confirmation before plan preparation, emergency handoff, and refusal
when a structured classifier tries to turn a greeting or unclear message into
a service action. These are offline policy tests, not Workpeg AI or hosted
acceptance evidence.
