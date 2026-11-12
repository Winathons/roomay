# WOR-19 — In-app Vapi voice call (local QA)

This adds an explicitly enabled Vapi Web SDK call to the existing loopback-only
My Stay example. It does not add a Workpeg route, guest-authentication service,
hotel writer, or production endpoint. The synthetic stay remains isolated in
`tools/guest_chat_demo.py`.

## What the local feature does

- The chat header shows a small **Call Remi** button. The orb is not displayed
  or animated in the normal My Stay conversation panel. Clicking this button
  explicitly opens a centered accessible voice-call dialog; when the Vapi test
  assistant is configured, the same click also initiates the call. If Vapi is
  unconfigured, opening the dialog previews the orb without starting audio.
  The dialog contains the orb, elapsed call time (starts on confirmed
  `call-start`), visible call status, captions, Mute, End Call and Close.
  Closing by the button, Escape or backdrop ends/cancels an active or pending
  call, and late provider events cannot restart it. The orb animation is paused
  while the dialog is hidden. No provider request starts on page load.
- Connecting, listening, speaking, ended, unavailable, and sanitized error
  states are shown. The guest can mute the microphone, interrupt the assistant,
  and end the call.
- The Claude-provided Roomay Orb custom element is visual only. `connecting`,
  `ready`, `muted`, ended, unavailable and error map to its idle animation;
  only a connected listening state or Vapi assistant speech activity maps to
  listening or speaking. Muting never starts a second audio stream. A static
  CSS orb remains behind the component if canvas/custom-element rendering is
  unavailable, and the live textual status remains accessible.
- The call is limited to 180 seconds and at most three starts per example
  session. The server allows one active call claim per session. These local
  guards reduce accidental usage; they are not account-wide billing controls.
- Final user transcripts appear as captions in the browser. The guest may
  explicitly copy the latest transcript to the editable request composer. It is
  not automatically submitted. Sending then uses the existing deterministic
  conversation intake; the guest must still review and confirm. Resulting
  actions remain in-memory example state and are not sent to hotel staff.
- Existing on-device/consented browser dictation and typed chat remain
  available. The normal composer presents one microphone icon; if local en-NG
  recognition cannot run, its click opens a just-in-time consent dialog before
  starting the browser's speech service. Declining leaves typed chat available.
  The provider disclosure does not replace the browser's microphone permission
  prompt. Call audio is not recorded or stored by Roomay.

## Local build and launch

The Vapi browser dependency is pinned to `@vapi-ai/web` 3.1.0 and bundled into
`tools/guest_chat_demo_assets/vapi_sdk.js` for same-origin serving. To rebuild
it after changing the SDK entry:

```powershell
Push-Location tools/guest_chat_demo_assets
npm ci
npm run build:vapi
Pop-Location
```

The orb runtime is served locally as `/roomay-orb.js`. Only the 18-KB JavaScript
component is included; the kit's GIF, MP4, preview HTML and alternate Lottie
assets are not shipped by the local page.

Use a Vapi **public** API key (or a restricted public JWT), the existing test
assistant ID, and confirm in the Vapi dashboard that this saved test assistant
actually uses YarnGPT voice `remi` before setting the voice assertion. Never
use a private API key here.

```powershell
$env:ROOMAY_VAPI_PUBLIC_KEY = '<Vapi public key or short-lived public JWT>'
$env:ROOMAY_VAPI_TEST_ASSISTANT_ID = '<ROOMAY GPT-4o STT Test assistant ID>'
$env:ROOMAY_VAPI_TEST_ASSISTANT_VOICE = 'remi'
$env:ROOMAY_VAPI_TEST_LLM_PROVIDER = '<verified saved assistant LLM provider>'
$env:ROOMAY_VAPI_TEST_LLM_MODEL = '<verified saved assistant LLM model>'
python -m tools.guest_chat_demo --port 8765 --enable-local-qa --enable-vapi-web-call
```

Open `http://127.0.0.1:8765/__qa/`, select **Guest**, then open My Stay and
press **Call Remi**. The actual call makes billable Vapi/model/transcriber/TTS
requests; do not run it until the owner has approved that usage and confirmed
the test assistant settings. The local server remains bound to loopback. The
Vapi public key should also be restricted in the Vapi dashboard to the local
origin (`http://127.0.0.1:8765`) and only this test assistant. The restriction
is a dashboard setting and is not verified by this code.

For an animation-only local preview without provider configuration, run the
server with `--enable-local-qa` but omit `--enable-vapi-web-call`; select Guest
and open My Stay. The orb is hidden until you click **Call Remi** in the chat
heading, then a visual-only dialog opens with a disabled provider connection
and the unchanged typed fallback. Close it with the × button, Escape or the
backdrop. The configured command above enables a call only after the guest
clicks **Call Remi**.

These startup settings are explicit operator assertions. Verify the test
assistant's saved Remi voice and LLM provider/model pair in the Vapi dashboard
first. The per-call override supplies Roomay's safety prompt and the same
LLM provider/model. Vapi documents same-provider `model.messages` overrides as
replacing the matching system message while preserving saved model settings.
If the provider/model differs from the saved assistant, do not start the call.
The override requests a 180-second maximum, disables audio recording, artifact
logging, transcript artifacts, and video, and enables interruptions. A
separate browser timer also ends the call.

No live Vapi call was made during implementation. CI mocks the SDK and all
voice-config/session endpoints.

## Credentials and production JWT path

- `ROOMAY_VAPI_PUBLIC_KEY` is intentionally returned only to the local Guest
  browser by a same-origin, session-scoped endpoint. A Vapi public key is
  designed for browser use, but should still be limited to the local origin and
  one test assistant in the Vapi dashboard.
- `ROOMAY_VAPI_TEST_ASSISTANT_ID` and `ROOMAY_VAPI_TEST_ASSISTANT_VOICE=remi`
  are local settings, not proof that the assistant has Remi attached. Verify
  the assistant configuration manually; this task does not change it.
- No Vapi private key, YarnGPT key, Vapi bearer token, or guest-session secret
  is read by the browser-call feature. Do not set a Vapi private key in this
  local QA process.
- Production should request a short-lived **public** Vapi JWT from the
  authenticated Roomay backend. Vapi documents HS256 signing with the
  server-held private API key, an `orgId`, an expiry no more than one hour,
  `token.tag="public"`, `allowedOrigins`, and `allowedAssistantIds`. The JWT
  issuer must verify the real guest session before returning a token. Roomay
  does not yet have that verified guest identity boundary on this branch, so
  no production JWT endpoint is implemented.

## Audio, transcripts, logging, and cost

The local disclosure warns that audio leaves the browser for Vapi and that
provider processing/retention applies. The per-call SDK overrides request
recording, detailed artifact logging, transcript artifacts, and video
recording to be disabled. This has not been verified against a live call or
organization policy. Vapi still creates call/session records and may retain
operational metadata, billing information, or provider telemetry. The SDK
transcript events are rendered locally and are only sent to Roomay's local
example intake if the guest explicitly selects **Use my latest transcript**
and then presses the existing Send control. Do not speak real guest or payment
information in a test call. Check Vapi's current account retention/ZDR terms
and the saved assistant's artifact settings before an owner-approved call.

## Text AI evaluation (Phase B)

Vapi's documented `POST /chat` requires server-side private-key auth and accepts
`assistantId`, text input, and either `previousChatId` or `sessionId` for
multi-turn context. The Chat API is not implemented here. Vapi documents chat
logs containing input, output, prior messages, assistant, and cost; chat
logging has no separate on/off switch. Adding it to Guest chat therefore needs
an owner-approved provider-data/retention decision and a server-side authenticated
guest integration. It must remain separate from deterministic action
classification; model output cannot confirm or persist a hotel operation.
Until then, the safe deterministic chat remains available if a provider is
unconfigured or unavailable.

## Verification and remaining boundaries

`tests/vapi_web_call.cjs` drives the browser controller against a mocked Web
SDK, microphone errors, timers, and fetch. `tests/test_guest_chat_demo.py`
checks that voice is off by default, session and same-origin gates apply, the
call cap works, and only public configuration is returned. No physical
microphone, real Vapi request, YarnGPT call, Workpeg API, or hosted data is used
by tests.

This does not establish real guest authentication, a verified active stay,
Workpeg authorization, a submitted or persisted request, a staff notification,
or a functioning production call. Production guest voice remains blocked on
WOR-15/WOR-17/WOR-61/WOR-62/WOR-65 and the approved persistence/authentication
path. The selected Remi voice remains dependent on owner verification of the
test assistant's saved TTS configuration; this code does not modify the
assistant or the Railway YarnGPT service.

## Official references checked

- [Vapi Web calls](https://docs.vapi.ai/quickstart/web)
- [Vapi Web SDK source and API](https://github.com/VapiAI/client-sdk-web)
- [Vapi JWT authentication and public restrictions](https://docs.vapi.ai/customization/jwt-authentication)
- [Vapi assistant overrides](https://docs.vapi.ai/assistants/assistant-overrides)
- [Vapi call artifact plan](https://docs.vapi.ai/assistants/call-recording)
- [Vapi Create Chat](https://docs.vapi.ai/api-reference/chats/create)
- [Vapi Chat session management](https://docs.vapi.ai/chat/session-management)
- [Vapi Chat logs and retention](https://docs.vapi.ai/observability/logs/chat-logs)
