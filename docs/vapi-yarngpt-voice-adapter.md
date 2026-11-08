# WOR-56 Phase A — Vapi and YarnGPT voice adapter

This is a standalone, offline-tested WSGI endpoint for Vapi custom TTS. It is
not a Workpeg route, Workpeg Function, deployed service, or live AI
integration. The endpoint synthesizes text only; it does not receive guest
requests, create hotel tickets, write Workpeg data, transcribe speech, or
confirm bookings. Vapi remains the call orchestrator and Azure Speech `en-NG`
remains the planned initial transcription provider.

## Architecture

`voice_adapter.wsgi.create_app()` implements Vapi's documented `POST` JSON
`message.type = "voice-request"` contract and returns raw
`application/octet-stream` PCM. It checks a Vapi bearer credential before
reading the request body, validates the text and timestamp, and bounds the body
and provider wait. Vapi's requirements table lists 8,000, 16,000, 22,050 and
24,000 Hz, while its example validator also includes 44,100 Hz. The adapter
accepts those five values to cover both parts of the official page; re-check
this discrepancy against the current Vapi deployment before hosted testing.

`voice_adapter.yarngpt.YarnConversationClient` calls YarnGPT's documented
`POST /api/v1/streaming/conversation` endpoint with `output_format: "pcm"`.
The upstream stream must report `audio/l16; rate=<N>; channels=1`. The adapter
rejects other content types, missing/invalid rate metadata, stereo and empty
audio. It converts the returned signed 16-bit little-endian mono PCM using a
stateful linear interpolator and streams the converted bytes to Vapi. A client
disconnect closes the upstream response when the WSGI server closes the
response iterable. For a Vapi payload carrying `call.id`, a per-turn
HMAC-derived `Idempotency-Key` is sent to YarnGPT without exposing call IDs or
text in the key. It is keyed with the server-side YarnGPT API key. Payloads
without a call ID use a random key and therefore do not deduplicate across
Vapi retries. No automatic retries are made after provider or network errors;
a partially delivered stream cannot be represented as a clean HTTP error after
the response starts.

The converter is deliberately small and dependency-free. Its sample-rate and
byte-format behavior is covered with synthetic audio, but it is not yet
accepted as voice-quality production resampling. Listening and telephony
quality measurements are required before deployment.

## Voice selection and provider IDs

YarnGPT documents that voice IDs are exact, case-sensitive values from its
authenticated `GET /api/v1/voices` catalogue, and that the catalogue changes.
The current docs example uses `umar`, but that is not a stable guarantee. The
docs do not publish stable Mary or Remi IDs. Since this task forbids live API
calls, no current Mary/Remi/Umar ID was verified and none is hard-coded.

Before deployment, an authorized owner must use YarnGPT's authenticated voice
catalogue to verify the exact current provider ID corresponding to each
owner-approved Mary, Remi and Umar voice. Configure the exact values in the
server's secret/configuration store as `YARNGPT_VOICE_MARY`,
`YARNGPT_VOICE_REMI` and `YARNGPT_VOICE_UMAR`. The adapter accepts assistant
IDs in `ROOMAY_VAPI_ASSISTANT_VOICE_MAP` as a JSON object mapping a saved Vapi
assistant ID to one of the aliases `mary`, `remi` or `umar`; unmapped requests
use `ROOMAY_TTS_DEFAULT_VOICE`. The assistant ID selects only among the
server-configured voice IDs and is not treated as authentication.

## Future deployment and Vapi setup

No endpoint or key is created by this change. After review and a separate
deployment authorization:

1. Select a private managed Python WSGI service with HTTPS, request-size
   limits, bounded concurrency, health monitoring and secret-manager support.
   The repository currently adds no WSGI server/runtime dependency; choose and
   review one for the target host instead of deploying this module directly
   from the Workpeg UI or Peg Function runtime.
2. Configure `ROOMAY_VAPI_BEARER_TOKEN` with a randomly generated secret of at
   least 32 characters and `YARNGPT_API_KEY` with the YarnGPT server key. Put
   both only in the host's secret manager. Never put the YarnGPT key in Vapi,
   browser code, this repository, Workpeg, call logs or assistant metadata.
3. Configure the three `YARNGPT_VOICE_*` IDs only after the owner has matched
   each ID to the approved sound in the current YarnGPT catalogue. Set
   `ROOMAY_TTS_DEFAULT_VOICE`, the optional assistant-ID mapping, and an
   appropriate `YARNGPT_TIMEOUT_SECONDS` (1–60).
4. Mount `voice_adapter.wsgi.create_app(VoiceConfig.from_environment())` at a
   stable HTTPS path such as `/synthesize`. Restrict access to POST, keep
   request/response bodies out of access logs, and ensure disconnects close
   WSGI iterables. The implementation has no admin, diagnostics, health-data,
   or CRUD route.
5. In Vapi, keep the existing assistant/call orchestration and Azure Speech
   `en-NG` transcription settings. Set the voice provider to `custom-voice`,
   the server URL to the HTTPS path, and attach a Vapi Custom Credential using
   a Bearer Token with the `Authorization` header and `Bearer` prefix enabled.
   Store only the Vapi-to-adapter bearer credential in Vapi; YarnGPT credentials
   stay on the adapter host. Use the saved assistant configuration so Vapi's
   configured credential is attached.
6. Start with a controlled internal test call and short, non-sensitive text.
   Do not connect guest calls or enable hotel actions until the separate
   operational and privacy review passes.

Vapi and YarnGPT docs may evolve. Re-check the current endpoint payload,
credential attachment rules, limits, PCM header and voice catalogue before
each hosted trial.

## Offline tests and future voice evaluation

`tests/test_voice_adapter.py` injects fake clients/responses and synthetic
PCM. It makes no DNS request, live provider request, call, credit charge or
Workpeg call. It covers all five accepted Vapi output rates, chunk boundaries, invalid
credentials/configuration, malformed request shapes, empty audio, provider
failure, rate limiting, invalid provider audio, timeout/disconnect cleanup,
and upstream request shape.

After a separately authorized deployment and provider trial, compare Mary,
Remi and Umar with the same short, non-personal test phrases and the same call
conditions. For each voice, record time to first audio byte and total synthesis
latency (p50/p95), completed/failed/timed-out calls, malformed or truncated
streams, Vapi playback quality, interruption behavior and YarnGPT's actual
usage/credit charge. Repeat across the required Vapi sample rates. Capture
only timestamps, selected voice alias, sample rate, durations, byte count,
HTTP outcome, retry-after and provider request trace ID; do not retain call
text, phone number, transcripts, guest identifiers, credentials or raw audio
unless separately approved. Read current charges from the provider account;
do not assume a fixed per-character or per-call price. YarnGPT notes its API
has no sandbox/test key and provider calls spend credits, so every real trial
requires the owner to approve the spend first.

## Current limitations and release gates

- No YarnGPT request, Vapi call, voice catalogue query, key generation, public
  deployment or credit use has occurred in this phase.
- Current Mary/Remi/Umar provider IDs, account access, voice availability,
  billing, real latency, reliability and pronunciation remain unverified.
- Azure Speech `en-NG` remains the intended Vapi transcription choice; this
  adapter does not configure or test transcription.
- Voice conversion is offline-verified but has not been reviewed by a speech
  engineer or tested by listening over the intended telephony path.
- WSGI server behavior for timeout enforcement, backpressure, concurrency,
  TLS, request logging and disconnect closure must be verified on the chosen
  host. A mid-stream failure can only terminate the stream; do not auto-retry
  or claim the caller heard the full response.
- No hotel intent, authorization, guest identity, or Workpeg persistence is
  handled. A future voice conversation flow must separately use
  `domain/conversation_intake.py`, verify the active stay with a trusted
  server-side adapter, request guest confirmation and hand off emergencies to
  a monitored human process. This adapter itself never creates a service
  request or claims it was submitted.

## Official references

- [Vapi custom TTS](https://docs.vapi.ai/customization/custom-voices/custom-tts)
- [Vapi server authentication](https://docs.vapi.ai/server-url/server-authentication)
- [YarnGPT API](https://yarngpt.ai/api-docs)
