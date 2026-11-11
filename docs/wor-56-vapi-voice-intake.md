# WOR-56 — Vapi voice receptionist tool boundary

## Scope and current behavior

`voice_adapter.intent_tools.create_tool_app()` is a separate WSGI endpoint for
Vapi's documented `POST` `message.type = "tool-calls"` Server URL protocol. It
is not the existing YarnGPT custom-TTS `voice-request` endpoint. It validates a
fixed function name and exact argument shape, routes only caller intent, and
returns one JSON-encoded result per `toolCallId` in Vapi's `results` array.
The existing `domain.conversation_intake.classify_text()` remains the source
for recognized service-request category/department routing.

The only supported function is `roomay_route_caller_intent`, with exactly one
argument, `utterance` (text, 1–1000 characters). The response is deliberately
small and contains state, a fixed caller-facing message, optional department,
and explicit `submitted: false` / `persisted: false` flags. It never echoes the
utterance, a room number, caller ID, guest profile, stay, or internal domain
object. Unknown tools and invalid server/router outcomes fail closed.

The routing outcomes are:

- Emergency or request for a person: `human_handoff`. The message explicitly
  says this endpoint did not contact or transfer the call.
- New reservation enquiry: `booking_enquiry`, routed to Reception. No prices,
  inventory, availability, booking, or confirmation are claimed.
- General public hotel question: `public_enquiry_unavailable`. There is no
  approved hotel facts/knowledge source in this endpoint, so it does not invent
  an answer.
- Recognized existing-stay service request: canonical department is returned
  with `guest_verification_required`. A room number or caller statement does
  not authenticate the guest; the endpoint does not inspect a stay or submit a
  request.
- Forgotten PIN or stay code: `verification_unavailable`. The endpoint does
  not ask the caller to speak a PIN and directs them to Reception.
- Ambiguous intent: one short clarification naming the four supported
  categories: hotel information, new booking, existing stay help, or human
  receptionist.

## Security controls and limits

Vapi provider authentication is a server-to-server boundary, not guest
authentication. `ToolConfig` requires a server-held bearer token with at least
32 characters. The handler authenticates before reading the body, limits JSON
requests to 32 KiB and four calls, accepts POST with JSON only, bounds utterance
size, applies a process-local aggregate request limit, and uses a bounded replay
cache keyed by `toolCallId`. Identical redelivery gets the prior sanitized
result; reusing the same ID with changed arguments fails closed. No request
content or exceptions are logged by this module.

The request limiter and replay cache live in one Python process. A deployed
multi-worker service must also apply shared rate limiting at its HTTPS edge;
the local limiter alone is not a distributed abuse control. The bearer
credential must be stored only in the host's secret store and the matching
Vapi Custom Credential. Request/response body logging must be disabled at the
reverse proxy and application server. This code does not supply TLS, a
production WSGI host, monitoring, or secret management.

The existing `GuestActionGateway` and guest-session authority are not invoked:
there is no verified Vapi caller session or trusted active-stay resolver
available here. Do not connect a guest session using caller ID, a name, a
spoken room number, AI output, or an unverified PIN. Before a future request
action, the backend needs an approved short-lived challenge/invitation flow,
trusted current-stay lookup, revocation, attempt limits, idempotent user
confirmation, Workpeg access and persisted request-plus-audit verification.
Until those gates pass, this endpoint is routing-only and cannot create a
hotel action.

## Vapi and YarnGPT configuration after separate owner approval

No Vapi assistant settings, function tools, endpoint, phone number or provider
account were changed by this PR. After review and deployment approval:

1. Host the WSGI tool endpoint at a stable HTTPS URL on an approved service.
   Configure `ROOMAY_VAPI_TOOL_BEARER_TOKEN` only in the host's secret store.
   Set `ROOMAY_VAPI_TOOL_REQUESTS_PER_MINUTE` to a reviewed ceiling and enforce
   an additional shared limit at the edge.
2. In Vapi Dashboard, create a **saved Function tool** named
   `roomay_route_caller_intent` with a required string parameter `utterance`,
   set its server URL to the hosted tool endpoint, and select a Custom
   Credential configured as Bearer Token / `Authorization` / Bearer prefix.
   Vapi's current docs state that saved tool/assistant URLs can use the
   referenced credential; URLs supplied transiently by an API call may not
   carry it. Keep credentials server-side and never put them in tool arguments.
3. Review the tool schema and caller prompts, then attach the saved tool to the
   existing Roomay assistant only after the hosted auth, rate-limit, abuse,
   and privacy review. Preserve existing assistant voice/transcriber settings;
   do not publish assistant changes until separately authorized.
4. Keep the existing Azure `en-NG` transcription selection. It is not tested by
   these offline tests. Do not silently substitute a locale or claim Pidgin
   transcription accuracy without measured call tests.
5. In the YarnGPT adapter host's environment set
   `ROOMAY_TTS_DEFAULT_VOICE=remi` and `YARNGPT_VOICE_REMI=remi`. `remi` is the
   owner-selected exact provider voice ID. Mary and Umar stay optional via
   `YARNGPT_VOICE_MARY` and `YARNGPT_VOICE_UMAR`; voice mappings may reference
   only aliases configured on that host. Keep `YARNGPT_API_KEY` on the server.
   No Vapi/YarnGPT calls, voice catalogue reads, charges, credentials, or
   assistant edits were made or tested here.

The existing TTS adapter remains at its separate custom voice endpoint. It
streams provider PCM and has its own Vapi bearer token (`ROOMAY_VAPI_BEARER_TOKEN`).
Do not reuse the tool bearer secret for TTS.

## Offline verification

`tests/test_voice_intent_tools.py` uses only synthetic tool-call fixtures and
injected routing failures. Together with `tests/test_voice_adapter.py`, the
focused suite covers the official Vapi envelope and result shape, bearer
rejection before body reads, public/booking/service/human routing, ambiguous
clarification, emergency, forgotten PIN, room-claim non-authentication, replay
and changed replay, malformed/unknown calls, request size/rate limits,
provider/router failure, privacy-safe outputs and no false submission. No
Vapi, YarnGPT, Workpeg, phone, or paid-provider network request is made.

## References

- [Vapi Server Events — Function Calling](https://docs.vapi.ai/server-url/events)
- [Vapi Server Authentication](https://docs.vapi.ai/server-url/server-authentication)
- [Vapi Function Tools](https://docs.vapi.ai/tools)
- [Roomay conversation intake](conversation-intake.md)
- [Roomay guest access contract](guest-access-contract.md)
- [Roomay Vapi/YarnGPT custom TTS adapter](vapi-yarngpt-voice-adapter.md)
