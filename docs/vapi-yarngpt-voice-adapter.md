# WOR-56 Phase A — Vapi and YarnGPT voice adapter

This is a standalone, offline-tested WSGI endpoint for Vapi custom TTS. It is
not a Workpeg route, Workpeg Function, deployed service, or live AI
integration. The endpoint synthesizes text only; it does not receive guest
requests, create hotel tickets, write Workpeg data, transcribe speech, or
confirm bookings. Vapi remains the call orchestrator. The owner reports that
the separate **ROOMAY GPT-4o STT Test** assistant uses provider **OpenAI** and
model **`gpt-4o-transcribe`**, with a Nigerian Pidgin transcription prompt.
English and Pidgin conversations were tested by the owner; recognition
improved but remains imperfect. This is owner-reported test evidence, not an
independent dashboard inspection or automated ASR result. The main published
assistant remains separate and unchanged. This repository does not configure
or validate the transcriber.

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
The owner has approved the exact YarnGPT voice ID `remi` for Roomay's default.
This change uses that value without making a live catalogue request. Mary and
Umar remain optional aliases and are not required to configure the adapter.

Before deployment, an authorized owner may confirm the selected voices in
YarnGPT's authenticated voice catalogue. Set `YARNGPT_VOICE_REMI=remi`;
optionally configure `YARNGPT_VOICE_MARY` and `YARNGPT_VOICE_UMAR` if those
voices should be available. The adapter accepts assistant
IDs in `ROOMAY_VAPI_ASSISTANT_VOICE_MAP` as a JSON object mapping a saved Vapi
assistant ID to one of the aliases `mary`, `remi` or `umar`; unmapped requests
use `ROOMAY_TTS_DEFAULT_VOICE`, which defaults to `remi`. The assistant ID selects only among the
server-configured voice IDs and is not treated as authentication.

## Hosting preparation and Vapi setup

The existing application is prepared for a separate Render Python web service;
this repository does not deploy or create that service. Render is a practical
low-cost fit because its Python web services support WSGI/Gunicorn, managed
HTTPS, secret environment variables and long-lived HTTP streaming. Render's
docs describe streaming HTTP/SSE responses, but the end-to-end behavior of the
deployed load balancer and this PCM body has not been measured. A chunk-arrival
test remains a deployment gate; do not infer streaming from a successful HTTP
status alone.

`render.yaml` is the prepared service definition. It uses the existing
`voice_adapter.tts_wsgi:application`, Python 3.13.5, the paid `0.5c-512mb`
compute plan, one instance, one Gunicorn `gthread` worker with two request
threads, bounded listener/header settings, and automatic deployment disabled.
Frankfurt is selected as the closest currently documented Render region to
Nigeria; check YarnGPT and Vapi network latency before creating the service,
because Render does not allow changing a service's region after creation. The
current estimated compute cost is about **US$7/month**, before bandwidth,
taxes, future price changes, YarnGPT usage, or any other provider costs. The
free plan is not recommended for the first real call because cold starts and
limited resources make voice latency and stream reliability unsuitable for
acceptance.

The isolated `requirements-voice.txt` installs only the pinned Gunicorn WSGI
server; the adapter itself uses Python's standard library. The repository's
Workpeg development pin is unchanged. For a manually configured Render service,
use:

```text
Root Directory: .
Runtime: Python
Region: Frankfurt
Instance: 0.5c-512mb (one instance)
Build command: python -m pip install --no-cache-dir -r requirements-voice.txt
Start command: gunicorn voice_adapter.tts_wsgi:application --bind 0.0.0.0:$PORT --worker-class gthread --workers 1 --threads 2 --worker-connections 16 --backlog 16 --limit-request-line 4094 --limit-request-fields 64 --limit-request-field_size 4096 --timeout 75 --graceful-timeout 25 --access-logfile - --access-logformat '%(m)s %(U)s %(s)s %(L)s'
Automatic deploys: Off
Health check: Render TCP port check (no extra app route is added)
```

The access-log format contains only method, URL path (no query), status and
elapsed time. It omits caller IP, request line, query, headers, referrer, user
agent, body and response body. Do not add proxy/body logging or debug tracing.
Render's `sync: false` secret declarations intentionally prompt an owner for
the two secret values during initial Blueprint setup; they contain no
credentials in this repository. Configure these server environment values:

| Variable | Value / handling |
| --- | --- |
| `YARNGPT_API_KEY` | YarnGPT API key; host secret only, never put in Vapi |
| `ROOMAY_VAPI_BEARER_TOKEN` | Independently generated random value, at least 32 characters; host secret and Vapi Custom Credential |
| `ROOMAY_TTS_DEFAULT_VOICE` | `remi` |
| `YARNGPT_VOICE_REMI` | `remi` |
| `YARNGPT_TIMEOUT_SECONDS` | `20`; per-operation socket timeout, 1–60 seconds |
| `ROOMAY_TTS_RATE_LIMIT_REQUESTS` | `10` authenticated synthesis requests |
| `ROOMAY_TTS_RATE_LIMIT_WINDOW_SECONDS` | `60` seconds; bounded sliding window |
| `ROOMAY_TTS_SYNTHESIS_DEADLINE_SECONDS` | `25` seconds total from provider request through streamed PCM; allowed 1–120 seconds |
| `PYTHON_VERSION` | `3.13.5` |

The synthesis deadline starts before the YarnGPT request. It bounds connection
setup, first audio, and the complete PCM stream. Expiry closes the provider
response and prevents further PCM from being yielded. `YARNGPT_TIMEOUT_SECONDS`
continues to bound an individual blocked socket operation; Gunicorn's worker
timeout is only a worker-liveness setting. A partially streamed response cannot
be converted to a clean HTTP error after headers have been sent.

Do not place actual secrets in a shell command, `.env`, Blueprint, Vapi
assistant text, build log, or PR. Do not set the YarnGPT API key in Vapi.
The adapter applies a bounded sliding-window limit after bearer authentication
and before request parsing or provider use. Its state is process-local: it is
shared by threads in one Gunicorn worker, but it is not distributed between
workers, instances, or restarts. The prepared Render service uses one instance
and one worker; increasing either means each process gets an independent quota.
This is a cost/abuse safeguard, not a per-caller identity limit. Keep one worker
and one instance for the controlled test, retain a high-entropy shared bearer
credential, and monitor provider usage. A multi-worker/public deployment needs
an approved shared rate-limit service or edge limit and a provider spend alert.
Rate limiting is fail-closed: a full window returns HTTP 429 with a bounded
`Retry-After`; limiter errors return 503 without calling YarnGPT.

### Owner-controlled Vapi setup after hosting approval

Keep this limited to the **ROOMAY GPT-4o STT Test** assistant. The owner
reports that it currently uses OpenAI `gpt-4o-transcribe` with the Pidgin
transcription prompt; leave those transcription settings unchanged. The
published/main assistant is separate and must not be edited as part of this
trial.

1. In Vapi Dashboard → Integrations → Server Configuration, add a Custom
   Credential of type **Bearer Token**. Give it a descriptive name, enter the
   same `ROOMAY_VAPI_BEARER_TOKEN` that was entered into the hosting secret
   store, use header `Authorization`, and enable **Include Bearer Prefix**.
   Save it; do not paste the YarnGPT key here.
2. Open **ROOMAY GPT-4o STT Test** only. In its Voice settings, select provider
   `custom-voice`, set the server URL to `https://<approved-service-host>/synthesize`,
   select the credential just created, and set `timeoutSeconds` to 30.
3. Save the test assistant configuration, verify the credential is attached to
   this saved assistant configuration, and leave the main published assistant
   unchanged. Vapi documents that custom credentials are attached to saved
   assistant/server configuration, not arbitrary URLs supplied at request
   time.
4. Do not run a test call until the owner separately approves YarnGPT credit
   use. The first audio call uses a real provider request and is billable.

### Deployment checks without secrets, PII, or YarnGPT credits

After an owner-authorized service creation, these checks do not invoke YarnGPT:

1. Open the HTTPS service URL in a browser or request `GET /synthesize`. Expect
   HTTP 405 with `Allow: POST`; confirm plain HTTP redirects to HTTPS. This
   verifies routing/TLS and the app entry point, not audio generation.
2. Send a small unauthenticated POST with JSON content type and a synthetic
   body. Expect HTTP 401 and `{"error":"unauthorized"}`. Authentication is
   checked before the body is parsed or the provider is called. Inspect only
   status and safe response headers; do not enable request-body capture.
3. Confirm host environment-variable names/configured presence in the owner
   dashboard without opening, copying or screenshotting secret values. Check
   service logs for the minimal method/path/status/duration format only.

An authenticated PCM smoke test is intentionally **not** credit-free. Once the
owner approves the YarnGPT spend and Vapi test-assistant edit, send one short,
fictional, non-sensitive phrase. Record only HTTP status, content type, byte
count, time-to-first-byte, total time and whether chunks arrived incrementally.
Do not print the bearer value, output audio, request body or response body to
console. Stop on timeout, non-200 status, empty/truncated PCM, or if all bytes
arrive only after provider completion. Never automatically retry a timed-out
or interrupted call.

Render terminates incoming HTTPS at its load balancer and forwards HTTP to the
service process inside its hosting network. TLS-at-edge is verified by Render
documentation; this task does not evaluate Render's contractual/security fit
for production guest personal data. Before using real guest conversations,
complete vendor/privacy review, retention and data-processing review, regional
latency measurement, abuse/rate-limit review, and incident-response planning.

Vapi and YarnGPT docs may evolve. Re-check the current endpoint payload,
credential attachment rules, limits, PCM header and voice catalogue before
each hosted trial.

## Offline tests and future voice evaluation

`tests/test_voice_adapter.py` injects fake clients/responses and synthetic
PCM. It makes no DNS request, live provider request, call, credit charge or
Workpeg call. It covers all five accepted Vapi output rates, chunk boundaries,
invalid credentials/configuration, malformed request shapes, empty audio,
provider failure, bounded authenticated request rate, total synthesis deadline
during streaming, timeout/disconnect cleanup, response-resource closure, and
upstream request shape. These deterministic tests do not replace hosted latency
and disconnect verification.

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

## First-audio latency acceptance plan

The YarnGPT streaming client's default upstream read was reduced from 8,192 to
2,048 bytes to favor earlier first output. This is **not a measured speed
improvement**: network buffering, source PCM rate, Python resampling work, WSGI
server buffering, Vapi and caller connection can still dominate response delay.
Keep the source audio streaming; do not wait for the full synthesis to finish.

During a separately approved live trial, compare a native Vapi voice and the
YarnGPT custom-voice bridge under the same transcriber, model, prompt and
network conditions. For at least 10 short test interactions per voice, record:

- Caller speech-end to **first audible sound** (p50/p95), measured at the
  browser/caller, not inferred from HTTP response headers alone.
- YarnGPT upstream request to first PCM byte, adapter first response byte, and
  full audio completion, with no text/transcripts/phone numbers in logs.
- Interruption/barge-in stop time, stalled streams, disconnected-call cleanup,
  error rate, generated audio duration and per-call voice-provider charge.

The initial *engineering targets*, not guarantees, are first audible speech
typically under one second and p95 below 1.5 seconds. If that is not met,
investigate the STT endpointing window, model first-token delay, provider
buffering and geographic routing before buying infrastructure. Optimize with
measurements: reducing chunks can increase CPU/transport overhead and does
not guarantee lower latency. Never describe this offline-tested adapter as a
live low-latency hotel receptionist until the whole pipeline is tested.

## Current limitations and release gates

- This implementation made no YarnGPT provider request, voice-catalogue query,
  key generation, public deployment or credit use. The owner separately tested
  English/Pidgin conversations with the ROOMAY GPT-4o STT Test assistant; that
  assistant is not the main published assistant and is not connected to the
  YarnGPT Remi TTS bridge.
- The owner-approved `remi` ID is configured as default, but provider
  availability, account access, billing, real latency, reliability and
  pronunciation remain unverified because no live YarnGPT request was made.
- The owner reports the separate test assistant uses OpenAI `gpt-4o-transcribe`
  with a Nigerian Pidgin prompt. English/Pidgin conversation testing improved
  recognition but it remains imperfect. This adapter neither configures nor
  validates STT; transcript mistakes can still affect downstream intent
  routing. The main published assistant is separate and unchanged.
- YarnGPT Remi is not connected to the test or main published assistant yet.
  The adapter default alone does not mean Vapi is using Remi; a separately
  deployed HTTPS endpoint, Vapi credential attachment and playback test remain
  required.
- Voice conversion is offline-verified but has not been reviewed by a speech
  engineer or tested by listening over the intended telephony path.
- WSGI server behavior for incremental chunk delivery, backpressure, concurrency,
  proxy buffering, TLS, logging and disconnect closure remains unverified on a
  live Render service. The local adapter tests verify WSGI iterator streaming
  and upstream closure, not the host proxy. A mid-stream failure can only
  terminate the stream; do not auto-retry or claim the caller heard the full
  response.
- The prepared service bounds the request body/text and concurrent worker
  threads, but this adapter has no rate limiter. Add a reviewed request-rate
  control and spend alert before broader exposure.
- Hotel intent and caller routing are handled only by the separate
  `voice_adapter.intent_tools` boundary described in
  [the WOR-56 voice intake notes](wor-56-vapi-voice-intake.md). This TTS
  adapter does not authenticate a guest or persist hotel operations. A future
  voice request flow must verify an active stay through a trusted server-side
  adapter, use the shared action gateway, persist request and audit state, and
  hand off emergencies through a monitored human process.

## Official references

- [Vapi custom TTS](https://docs.vapi.ai/customization/custom-voices/custom-tts)
- [Vapi server authentication](https://docs.vapi.ai/server-url/server-authentication)
- [YarnGPT API](https://yarngpt.ai/api-docs)
- [Render web services](https://render.com/docs/web-services)
- [Render TLS](https://render.com/docs/tls)
- [Render Blueprint reference](https://render.com/docs/blueprint-spec)
- [Render Python version](https://render.com/docs/python-version)
- [Render pricing](https://render.com/pricing)
- [Gunicorn installation](https://gunicorn.org/install/)
- [Gunicorn logging](https://docs.gunicorn.org/en/stable/settings.html#access-log-format)
