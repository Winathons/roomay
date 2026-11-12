# WOR-18 — natural guest chat and validated request intake

## What this change does

The loopback-only Guest My Stay page now uses a messaging-style composer. Text
and reviewed speech transcripts enter the same `/api/message` conversation. A
message is not automatically a hotel request: greetings and ordinary
conversation stay in chat; recognized service needs, hotel-information
questions and emergencies take the existing deterministic intake/handoff path.

The existing `domain.conversation_intake` contract remains responsible for
trusted stay/room checks, canonical category-to-department routing and explicit
confirmation. The Vapi model cannot select a department or authorize an action.
Only after guest confirmation does the local example prepare the existing
canonical request/audit plan in its isolated process-memory test store. That is
not Workpeg persistence and never means staff received a request.

Unrecognized ordinary conversation does not become a request just because it is
long. When it is explicitly enabled and separately consented to, Remi can answer
ordinary text using Vapi Chat. Recognized service requests, room/availability
questions and emergency phrases are deliberately not sent to that provider.
Property information is answered only from the hotel's verified records; this
local example has no verified breakfast, price, availability, or amenity facts,
so those questions direct the guest to Reception without a model-generated
answer.

## Vapi Chat status and constraints

Vapi documents `POST https://api.vapi.ai/chat` as **Beta**. The server authenticates
with a private Vapi API key. Multi-turn context is continued with
`previousChatId`; the browser never receives the key or provider chat ID. The
local demo stores the last chat ID only in its server-side, short-lived synthetic
session, and drops the provider context when a hotel action or consent revocation
occurs.

Chat history has no separate disable switch in Vapi. Chat logs can include the
input, output, loaded prior messages, assistant and cost, subject to the Vapi
account's history/retention configuration. Usage may be billable, including the
selected model's provider charges. Vapi documents usage-based billing
requirements for Chat; verify the current account billing and prices before an
owner-approved live test. No request text is sent to Vapi until the local
operator has enabled the feature **and** the guest has turned on the explicit
“Use Remi AI” checkbox. Do not enter real guest, payment, health, or identity
information in this local example.

The saved test assistant must already be suitable for hotel text chat. Its
owner-reviewed system instructions should direct Remi to follow the guest's
current language (English or Nigerian Pidgin), keep ordinary conversation
natural, avoid claiming hotel facts unless supplied by verified data, never say
a request/booking/staff notification succeeded, and direct operational requests
back to Roomay's explicit review/confirmation flow. The Chat API's documented
assistant override for chat supports variable substitution only; this code
does not try to override a system prompt or modify the saved/published assistant.

If the response suggests that a request, booking, staff assignment, or
notification has been completed, Roomay discards that response and shows a
fixed unavailable message. The model has no tools and no hotel-write pathway.
This text filter is a defense in depth, not a replacement for a safe assistant
prompt or a real authorized backend.

## Local test setup (not production)

Provider use remains off unless all of the following are true:

1. The owner approves Vapi Chat use, message processing/retention, and possible
   charges.
2. A Vapi test assistant suitable for Roomay text is selected and its prompt is
   reviewed. Do not reuse or alter the published phone assistant without
   separate approval.
3. The local process receives these variables through a private shell/secret
   manager, not source code, browser JavaScript, command history, or Git:

   - `ROOMAY_VAPI_CHAT_PRIVATE_KEY`
   - `ROOMAY_VAPI_CHAT_ASSISTANT_ID`

4. Start the loopback QA journey with both opt-in flags:

   ```powershell
   $env:ROOMAY_VAPI_CHAT_PRIVATE_KEY = '<private Vapi API key>'
   $env:ROOMAY_VAPI_CHAT_ASSISTANT_ID = '<reviewed test assistant ID>'
   ..\roomay\.venv\Scripts\python.exe -m tools.guest_chat_demo --port 8765 --enable-local-qa --enable-vapi-chat
   ```

   Run from the feature worktree shown in the PR instructions, adjusting only
   the path to the repository's existing pinned environment. The command never
   starts a provider call by itself.

5. Open `http://127.0.0.1:8765/__qa/`, select **Guest**, open **My Stay**, and
   explicitly enable “Use Remi AI for this conversation.” Disable it to revoke
   further provider use and clear the stored provider conversation pointer.

Without those environment variables and the command flag, the checkbox stays
hidden and no Vapi request is made. Typed chat, speech-to-text, Call Remi, and
the existing request review flow remain available as before.

## Safety and product boundaries

- The Chat endpoint is exposed only as a server-side client in the loopback QA
  process. It is not a new public or Workpeg route.
- Provider access is consent-gated per synthetic guest session, limited to 30
  chat turns in that session, bounded by a 12-second request timeout and a
  bounded response size. There is no automatic retry.
- Known service requests are validated by Roomay and are not sent to Vapi Chat.
  The provider does not receive the verified guest name, stay, business,
  authoritative room mapping, internal IDs, request plan, or audit history.
- Emergencies use the existing human handoff copy. The app never reports that
  anyone was contacted.
- If AI is disabled or unavailable, ordinary chat has a clearly limited local
  response. Provider failure cannot create an action or success message.
- Service requests prepared in the QA journey are fictional, in-memory examples.
  Guest authorization, Workpeg persistence, department permissions, committed
  hosted audit events, and guest status after a real reload remain blocked on
  WOR-15/WOR-61/WOR-62/WOR-65.

## Official references checked

- [Vapi Create Chat (Beta)](https://docs.vapi.ai/api-reference/chats/create)
- [Vapi Chat quickstart](https://docs.vapi.ai/chat/quickstart)
- [Vapi session management](https://docs.vapi.ai/chat/session-management)
- [Vapi Chat logs](https://docs.vapi.ai/observability/logs/chat-logs)
- [Vapi logs, retention and ZDR](https://docs.vapi.ai/observability/logs/overview)
- [Vapi pricing](https://vapi.ai/pricing)
