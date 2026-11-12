# WOR-19 Phase A — Accessible browser voice intake

## Scope and preview

This prototype extends the existing **WOR-57 local guest-chat demo** only. It
does not add a route to the Workpeg Peg, change the receptionist, or connect to
hosted Workpeg. From the repository root, launch the existing loopback server:

```powershell
..\.venv\Scripts\python.exe -m tools.guest_chat_demo
```

Open the printed `http://127.0.0.1:8765/` URL. The page remains labeled
**OFFLINE DEMO — SYNTHETIC DATA — NO REQUEST SUBMITTED**.

## Supported browser mechanism and privacy

The Workpeg 0.152.0 UI compiler produces browser JavaScript, but the guest chat
is a standalone static HTML/JavaScript preview served by
`tools/guest_chat_demo.py`; it is not a Workpeg UI route. Voice input uses the
browser Web Speech `SpeechRecognition` API. Browser support is limited and
varies by browser, operating system, microphone permission and installed
language packs. The page feature-detects the API and always leaves typed input
available.

On-device en-NG dictation is preferred whenever the browser exposes
`processLocally` and `available()` reports an installed local pack. The page
never downloads a pack. The normal guest chat shows a single compact mic icon,
not a technical description or persistent browser-service checkbox. Clicking
the mic starts verified local dictation and triggers the browser's microphone
permission prompt when needed. If local recognition is unavailable, the click
instead opens a short, explicit provider-processing consent dialog. Only after
the guest chooses **Continue with browser speech** does recognition start;
microphone permission alone is not consent to remote processing. The browser
may transmit audio to its speech provider and that provider's privacy and
retention terms apply. ROOMAY does not collect/store raw microphone audio.
The guest can decline and continue typing. The disclosure never starts a
remote speech request automatically on page load.

The availability check does not request microphone access. Recognition starts
only from the user's microphone click or their affirmative dialog click. A denied permission, unavailable provider or device, language issue,
interruption, or empty result produces a status message and leaves typed input
available. Recognized text is placed in the existing editable composer and is
not submitted until the guest presses Send. See [MDN SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition),
[MDN on-device recognition](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API/Using_the_Web_Speech_API#on-device_speech_recognition),
and [MDN `processLocally`](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition/processLocally).

## Guest flow

1. The guest starts voice input with a direct button press.
2. The browser appends recognized text to the existing message field. This
   preserves typed content and edits if the guest starts another recording;
   it does not send that text automatically.
3. The guest can edit the transcript, or choose “Discard voice text” to restore
   the composer contents from before that recording, then press “Send reviewed transcript”
   (or use the existing keyboard submit behavior). Text is limited to 1,000
   characters and is passed to the existing WOR-57 handler, which calls the
   WOR-18 validated `handle_conversation_turn()` contract.
4. The existing demo asks for clarification or presents its canonical request
   summary and requires a separate guest confirmation before preparing an
   in-memory synthetic request plan.

The browser never supplies a verified guest identity. The local demo uses its
existing server-side fictional session. All result states remain
`submitted=False` and `persisted=False`; no ticket, notification, booking, or
Workpeg row is created.

## Accessibility and tests

The controls are semantic buttons with clear names and pressed state. Voice
availability, permission failures, and recognized-transcript readiness are
announced through a polite live region. The transcript stays in the labelled,
editable textarea; keyboard chat submission and all existing typed-input
functionality remain available. The UI prevents sending while recognition is
still listening, rejects overlong text before making the local intake request,
and keeps the submit busy guard against duplicate submissions.

`tests/guest_voice_intake.cjs` executes the real browser controller and app
script with mocked DOM, browser-recognition, and HTTP responses. Scenarios
cover unsupported browser APIs, availability statuses and errors,
direct-gesture start, denied permission, interrupted and empty speech,
overlong text, transcript editing/discard and preservation across another
recording, remote-service consent and provider availability, explicit send,
duplicate submit suppression, and a privacy-limited request body.
`tests/test_guest_chat_demo.py` verifies
the static script, MIME type, CSP and accessible controls. No physical
microphone, external service, Workpeg API, or production data is used by CI.

## What remains unverified

- The original dictation implementation was physically tested in Chrome using the prior checkbox UI; the compact microphone and contextual consent layout still require a separate owner browser check. The available desktop
  browser routed loopback navigation to a proxy 404, so rendered-browser and
  screenshot checks could not be completed. The mocked controller and direct
  local HTTP checks passed. Before release, manually test a supported browser
  with local `en-NG` dictation or choose the explicit browser-service opt-in;
  verify permission denial, stop, interruption, transcript editing and discard.
  Browser support and the `en-NG` pack vary by browser and operating system.
  See [MDN
  SpeechRecognition.available()](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition/available_static)
  for the supported status values and options.
- Pidgin/Nigerian-accent transcription quality has not been tested. The WOR-18
  Pidgin text classifier tests are not speech-recognition evidence.
- This demo is not a guest authentication service or production guest portal.
- Real guest requests still require the trusted guest-session, Workpeg
  authorization, hosted persistence, concurrency and audit reconciliation
  gates. WOR-28/WOR-14 remain blockers; this prototype cannot submit real
  requests.
- WOR-56 covers Vapi custom text-to-speech output; it is not modified here and
  does not provide browser microphone input. A future Vapi inbound voice
  adapter must use the same validated WOR-18 action contract after guest
  authentication and Workpeg write support exist.
