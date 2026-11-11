# WOR-56 — Vapi voice receptionist tool boundary

## Scope and current behavior

`voice_adapter.intent_tools.create_tool_app()` is a separate WSGI endpoint for
Vapi's documented `POST` `message.type = "tool-calls"` Server URL protocol. It
is not the existing YarnGPT custom-TTS `voice-request` endpoint. It validates a
fixed function name and exact argument shape, routes only caller intent, and
returns one flat string per `toolCallId` in Vapi's `results` array. The
successful `result` string contains JSON with the structured routing outcome;
the `response_language` is selected from the current utterance, so the
assistant can follow English, Nigerian Pidgin, or a language switch on the
next turn. This is conservative text classification, not speech-language
recognition: it relies on the transcript Vapi sends.
The existing `domain.conversation_intake.classify_text()` remains the source
for recognized service-request category/department routing.

The only supported function is `roomay_route_caller_intent`, with exactly one
argument, `utterance` (text, 1–1000 characters). The response is deliberately
small and contains state, a fixed caller-facing message, optional department,
`response_language`, and explicit `submitted: false` / `persisted: false`
flags. It never echoes the
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
result; reusing the same ID with changed arguments fails closed. For a
well-formed request with a usable call ID, unknown tools, invalid arguments,
rate limiting, replay conflicts and internal routing failures return HTTP 200
with `{ "results": [{ "toolCallId": "…", "error": "…" }] }`. This is the
Vapi tool-specific error contract: each item uses either a flat string
`result` or a flat string `error`, never both. A malformed outer envelope or
unusable call ID cannot be safely correlated and remains a sanitized HTTP 400;
failed provider authentication remains HTTP 401. No request content or
exceptions are logged by this module.

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
account were changed by this PR. The repository now exposes two independent
WSGI callables; an owner-selected host must provide HTTPS and a WSGI server.
They may share a hosting provider, but should run as separate services/processes
with separate secrets and separate Vapi credentials. Do not place either
provider key in the Workpeg UI, browser, function arguments, logs or Git.
After review and separate hosting/assistant-change approval:

1. Deploy the caller-intent WSGI app as one service with entry point
   `voice_adapter.tool_wsgi:application`. Its public POST URL should end in
   `/tool-calls` (the app also accepts `/`). Bind only
   `ROOMAY_VAPI_TOOL_BEARER_TOKEN` in that service's secret store and set
   `ROOMAY_VAPI_TOOL_REQUESTS_PER_MINUTE` to an owner-reviewed limit. Enable
   HTTPS, edge request-size/concurrency/rate limits, bounded timeouts, no
   request/response body logging, and secret redaction. The 32 KiB application
   limit and process-local limiter/replay cache do not replace shared edge
   controls. Do not expose an unencrypted origin.
2. In Vapi Dashboard → Tools, create a **saved Function tool** named
   `roomay_route_caller_intent`. Define the required server input `utterance`
   (1–1000 characters) and the Vapi-reserved required `bot_say`, set `strict: true`,
   `async: false`, and set the Server URL to the first service's HTTPS
   `/tool-calls` URL. Add a separate Vapi Custom Credential using Bearer
   authentication in the `Authorization` header; bind its secret to the same
   tool-service secret. Keep the Vapi test panel's credential limitation in
   mind: its browser-origin request may not use saved credentials, so do not
   weaken authentication or enable permissive CORS to accommodate it.
   Configure the function schema as:

   ```json
   {
     "name": "roomay_route_caller_intent",
     "description": "Classify the caller's current request. This reports intent only; it does not authenticate a guest, check live availability, book, contact staff, or submit hotel work.",
     "parameters": {
       "type": "object",
       "properties": {
         "utterance": { "type": "string", "minLength": 1, "maxLength": 1000 },
         "bot_say": {
           "type": "string",
           "description": "One brief, natural acknowledgment in the caller's current language. Do not claim that a booking, request, transfer, or other action has succeeded."
         }
       },
       "required": ["utterance", "bot_say"],
       "additionalProperties": false
     },
     "strict": true
   }
   ```
   Vapi's documented `bot_say` dynamic tool message is spoken before execution
   and removed from the arguments sent to the server, so Roomay still receives
   exactly `utterance`. Add one `request-start` message with empty `content` to
   suppress a second/default filler. If Vapi does not remove `bot_say` from the
   actual tool-call payload, stop and review rather than weakening the handler.
3. Configure tool messages with `role: "system"` for model-generated
   completion/failure wording (do not put internal instructions in a spoken
   assistant-role message):

   ```json
   [
     { "type": "request-start", "content": "" },
     { "type": "request-complete", "role": "system", "content": "Use the structured tool result. Reply naturally in response_language: Nigerian Pidgin for nigerian_pidgin, English for english, and follow the caller's latest language switch. Preserve every state and safety limitation. Never say a request was sent, a booking confirmed, staff contacted, or a transfer completed unless the result explicitly proves it; this tool never does." },
     { "type": "request-failed", "role": "system", "content": "The tool failed. Tell the caller in their current language that this intent check did not complete and offer Reception. Do not claim any action happened and do not claim a transfer." }
   ]
   ```

   Set assistant instructions to answer in natural Nigerian Pidgin when the
   latest caller turn is Pidgin, in English when it is English, and follow
   switches. Preserve the exact meaning of `state`, `handoff_required`,
   `verification_required`, `submitted`, and `persisted`;
   never claim a request,
   booking, human transfer, or notification succeeded. If the structured
   outcome's `response_language` conflicts with the transcript, do not infer
   authorization or upgrade the outcome.
   The exact instruction text is a proposal for owner testing in Vapi; the
   model-generated message behavior has not been tested against a live call.
4. Separately deploy YarnGPT TTS as a second service with entry point
   `voice_adapter.tts_wsgi:application` and public POST path `/synthesize`.
   In that service only, bind `ROOMAY_VAPI_BEARER_TOKEN` and `YARNGPT_API_KEY`
   as separate secrets. Set `ROOMAY_TTS_DEFAULT_VOICE=remi`,
   `YARNGPT_VOICE_REMI=remi`, and a reviewed `YARNGPT_TIMEOUT_SECONDS` from 1
   to 60. Mary and Umar are optional via `YARNGPT_VOICE_MARY` and
   `YARNGPT_VOICE_UMAR`; only set them after separately confirming IDs. Do not
   reuse the Function tool credential. Apply the same HTTPS, rate/size limits,
   bounded concurrency, private logging and secret protections. YarnGPT's key
   never goes to Vapi: only the second service's Vapi bearer credential does.
5. In Vapi's Custom Credentials, create a **different** Bearer credential for
   the TTS service. In the existing assistant's voice configuration, set
   provider `custom-voice`, server URL to the second service's HTTPS
   `/synthesize` endpoint, select that TTS credential, and choose a bounded
   timeout. This is a proposed owner step only; this PR does not modify or
   publish the assistant. Keep Remi as the default voice. The TTS bridge returns
   raw mono signed 16-bit little-endian PCM at Vapi's requested sample rate.
6. Before any Talk call, verify both deployments and TLS using the selected
   host's own deployment status and edge checks (these apps do not add a health
   endpoint), confirm each Vapi credential is attached to the correct saved
   resource, and obtain approval for YarnGPT credit use. Create or use a draft/
   cloned assistant for the test; do not alter the published assistant. Then
   run one short internal controlled call with no guest or private information. Verify
   English, Pidgin, code-switching, tool failures, no false operation claims,
   Remi playback, disconnect handling, and sanitized logs. Stop on any
   mismatch. The first Talk test requires deployed hosting and a paid YarnGPT
   streaming request; it is not ready to run from this PR alone.

The owner reports that current Vapi transcription is **Soniox STT RT v5**.
This is an owner-reported dashboard setting, not independently inspected here.
Neither this intent tool nor this TTS adapter configures or validates STT.
Preserve that current setting unless the owner deliberately changes it. Do not
describe Azure Speech `en-NG` as active; Nigerian Pidgin transcription quality
and Soniox behavior still need controlled call evaluation.

The two endpoints have separate credentials and protocols. The Function tool
uses `ROOMAY_VAPI_TOOL_BEARER_TOKEN` and JSON results; the custom TTS endpoint
uses `ROOMAY_VAPI_BEARER_TOKEN` and streams PCM. Do not reuse the tool bearer
secret for TTS.

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
- [Vapi Function Tools and result/error response format](https://docs.vapi.ai/tools/custom-tools)
- [Vapi Function Tool troubleshooting](https://docs.vapi.ai/tools/custom-tools-troubleshooting)
- [Vapi Dynamic Tool Messages](https://docs.vapi.ai/tools/dynamic-tool-messages)
- [Vapi custom TTS](https://docs.vapi.ai/customization/custom-voices/custom-tts)
- [YarnGPT API](https://yarngpt.ai/api-docs)
- [Roomay conversation intake](conversation-intake.md)
- [Roomay guest access contract](guest-access-contract.md)
- [Roomay Vapi/YarnGPT custom TTS adapter](vapi-yarngpt-voice-adapter.md)
