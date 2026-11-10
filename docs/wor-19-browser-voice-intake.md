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

## Supported browser mechanism

The Workpeg 0.152.0 UI compiler produces browser JavaScript, but the guest chat
is a standalone static HTML/JavaScript preview served by
`tools/guest_chat_demo.py`; it is not a Workpeg UI route. No microphone widget
or new Workpeg API is assumed. Voice intake uses the browser Web Speech
`SpeechRecognition` API only when it exposes `processLocally` and the static
`SpeechRecognition.available()` method. Before enabling voice, the demo calls
`available({langs: ["en-NG"], processLocally: true, quality: "dictation"})`.
Only `"available"` enables the voice button. The API's `"downloadable"`,
`"downloading"`, `"unavailable"`, unknown, and rejected results all leave typed
input available. The demo never calls `install()` and never downloads a
language pack. Recognition sets `processLocally = true` and `lang = "en-NG"`;
there is no server-based recognition fallback.

This privacy limit matters: MDN documents that the default recognition mode
often sends audio to a server and that support is limited across browsers. Its
on-device mode keeps both audio and transcript on the device. This demo refuses
older/cloud-only recognition implementations and offers typed input instead.
See [MDN SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition)
and [MDN on-device speech recognition](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API/Using_the_Web_Speech_API#on-device_speech_recognition).

The static availability check does not request microphone access. Microphone
access is requested only when the guest directly clicks “Start voice input.”
A denied permission, unavailable device,
missing language pack, browser policy refusal, interruption, or empty result
shows a plain status message and leaves typed input available. Nothing in
Roomay captures or stores a raw audio blob. The browser itself controls
microphone access and on-device recognition.

## Guest flow

1. The guest starts voice input with a direct button press.
2. The browser appends recognized text to the existing message field. This
   preserves typed content and edits if the guest starts another recording;
   it does not send that text automatically.
3. The guest can edit the transcript and then press “Send reviewed transcript”
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
cover unsupported/cloud-only browser APIs, availability statuses and errors,
direct-gesture start, denied permission, interrupted and empty speech,
overlong text, transcript editing and preservation across another recording,
explicit send, duplicate submit suppression, and a privacy-limited request
body. `tests/test_guest_chat_demo.py` verifies
the static script, MIME type, CSP and accessible controls. No physical
microphone, external service, Workpeg API, or production data is used by CI.

## What remains unverified

- No real-browser or microphone test was performed by automated tests. A local
  manual browser trial is still needed on a browser/OS with an already
  installed on-device `en-NG` dictation pack, including permission-denial and
  interruption checks. Browser support for `available()` and the `en-NG`
  dictation pack varies by browser and operating system. See [MDN
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
