# WOR-18 Phase A — offline conversation intake contract

This document describes a **pure Python, offline contract** for accepting a
typed message or future telephone transcript and preparing a canonical Roomay
service-request plan. It does not call an AI provider, Vapi, Workpeg, a webhook,
or any persistence API. A result with `state="prepared"` is not a submitted or
persisted request.

## Existing domain contracts reused

`domain/conversation_intake.py` composes the existing contracts rather than
creating a second service-request model:

- `domain/service_requests.py::CATEGORY_DEPARTMENTS` and `route_category()`
  remain the source of categories and departments.
- `create_request()` remains the only way this layer builds a service request.
  It enforces the canonical request shape, `received` status, active registered
  occupant association, idempotency, and audit-event plan.
- `domain/access_control.py::AccessContext`, `authorize_access()`, and
  `authorize_hotel_snapshot()` validate the supplied business, guest, hotel,
  and active-stay scope. Their claims must come from a trusted adapter; this
  module does not authenticate anyone.

## Python interface

1. `classify_text(text)` is a small deterministic offline phrase classifier.
   It returns a structured suggestion using canonical categories and derives
   the department from `route_category()`.
2. A future AI adapter may instead pass `classifier_output` to
   `handle_conversation_turn()`. The exact allowed shape is:

   ```python
   {
       "intent": "service_request",  # room_enquiry, unknown, emergency
       "category": "air_conditioning",
       "department": "maintenance",
       "urgency": "normal",
       "room_number": "205",        # or None until clarified
   }
   ```

   The category and department must agree with the existing canonical route.
   A room number must be present in the original text; the model cannot invent
   or infer it. The assistant cannot supply a guest identity, stay ID, status,
   authorization claim, title, request ID, or replacement description. A
   deterministic title is derived from the validated canonical category and the
   original guest text is retained verbatim as the request description. For an
   unknown complaint, the guest's original text is retained in `category_detail`
   as well, matching the existing service-request contract.
3. `handle_conversation_turn()` accepts channel (`typed_chat` or `vapi`), stable
   conversation and turn IDs, a trusted timestamp, optional classifier result,
   guest confirmation, a trusted `AccessContext`, and `ConversationScope`.
4. `ConversationScope` holds the complete hotel snapshot, the verified active
   stay and room, the authenticated business mapping, and existing requests for
   duplicate detection. It is an internal adapter value, **not** a token or
   proof of authentication. Never construct it from browser fields, AI output,
   caller ID, QR code, or an unsigned Vapi tool call.

Public response fields (`state`, `message`, `clarification`, and
`handoff_required`) are separated from `internal`. Only the public message and
approved state should be sent to a guest. The `internal` object can include room
identity, failure codes, and a request plan containing guest identifiers; do not
serialize it to a guest channel or log it in an unrestricted transcript.

## States and behavior

| State | Meaning | Request plan |
|---|---|---|
| `needs_clarification` | The room number is absent/ambiguous or the issue is too vague. Ask one safe follow-up. | None |
| `awaiting_confirmation` | Active guest/stay/room scope is verified and the route is previewed; wait for explicit guest confirmation. | None |
| `handoff` | Emergency, room enquiry, unverified identity, or unsafe scope needs a human. | None |
| `prepared` | Guest confirmed; canonical `create_request()` produced a local request and audit plan. | Internal plan only; `submitted=False`, `persisted=False` |
| `duplicate` | An exact request with the deterministic key is already present in the supplied snapshot. | None; no second plan |
| `unavailable` | Invalid classifier output, provider failure/timeout, or validation failure. | None |

The module has no `submitted` or `persisted` state. Every result reports both
booleans as false. It does not invent a ticket number or present the provisional
domain request UUID as a guest-facing reference.

## Classification and routing examples

- Faulty or non-cooling AC → `air_conditioning` → Maintenance.
- Extra towels / linen → `extra_towels` → Housekeeping.
- A leaking pipe or plumbing issue → `plumbing` → Maintenance.
- A request for drinking/bottled water → canonical `room_service` → Food & Beverage;
  water leaks, pressure or unavailable hot water remain plumbing issues.
- Room availability/rate/enquiry → Reception human handoff; no availability,
  reservation, or booking confirmation is made.
- A clearly stated but uncategorized hotel complaint → canonical `unknown` →
  Reception with `triage_required=True`, after confirmation. Unknown text that
  does not clearly describe a hotel issue gets a clarification prompt and cannot
  become a request merely because it is long.
- Confirmation previews show a server-derived category title and the guest's
  exact description. A model cannot author the title or replace the description.
- Emergency language is checked before any classifier result. It triggers an
  urgent human handoff. Any classifier result marked urgent also hands off to a
  person. It does **not** create an `escalated` service request or claim that
  Roomay contacted staff or emergency services. The phrase rules are limited
  examples, not a dependable emergency detector; a real channel needs human
  monitoring and separate emergency testing.

Text examples include Nigerian English and Pidgin phrases such as “Abeg bring
extra towels” and “Water dey leak.” These only test text classification. They do
not test speech recognition, transcription quality, or Vapi call handling.

## Idempotency and timing

The key is a deterministic UUID derived from the trusted business ID, channel,
conversation ID, and stable confirmation-event/turn ID. The provisional request
ID is derived from that key and is only part of the internal plan. Re-delivery
must reuse the same event ID and the same trusted timestamp; a changed payload
with a reused key fails through the canonical service-request contract. Existing
requests are checked before a new plan is returned. Without a hosted unique
constraint or serialized writer, this offline key does not make concurrent
Workpeg operations safe.

## Integration gates and limitations

- A Workpeg trusted adapter must derive the actor, business membership, hotel
  mapping, stay, room, and timestamp from authenticated records. A browser-sent
  `AccessContext` or boolean verification flag is forgeable and must not be used.
- Current hotel rows do not themselves prove multi-hotel isolation inside one
  business. The trusted business-to-hotel mapping prerequisite from WOR-51 still
  applies.
- No AI provider or Vapi adapter exists here. A future Vapi adapter must verify
  its webhook/tool origin and separately bind the caller to a guest/stay; caller
  ID or speech content alone is insufficient.
- The current canonical request model records a guest origin, not a distinct
  typed-chat versus telephone channel. For a verified guest using Vapi, this
  contract keeps `origin="guest"`; channel is used in the idempotency key only.
  If channel attribution is required for audit or analytics, add a separately
  reviewed schema/domain extension rather than overloading another origin.
- No Workpeg request tables have been provisioned and no request/audit row has
  been created, submitted, or persisted by this code.
- Workpeg CRUD, role permissions, hosted serialization, write read-back,
  timeout reconciliation, request reload, and multi-role denial remain
  unverified under WOR-28/WOR-29/WOR-14.
- Real guest descriptions may contain personal or health information. Keep the
  internal plan private, define retention/redaction, and grant staff only the
  fields required for their role before any production use.

## Verification

`tests/test_conversation_intake.py` uses only the fictional `synthetic_hotel()`
fixture. It covers English/Pidgin text classification, room clarification,
active-stay and business checks, wrong department, explicit confirmation,
duplicate confirmation, emergency handoff, invalid provider output, timeout,
and the strict unsubmitted/unpersisted boundary. No audio, AI, Vapi, Workpeg, or
network calls are made.
