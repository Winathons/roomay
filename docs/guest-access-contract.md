# WOR-15 Guest Access Contract (Phase A)

This document describes offline, fail-closed contracts for future verified
guest chat and Vapi voice access. It is not a public guest service, Workpeg
login implementation, hosted permission policy, or proof of identity.

## Security boundary

`domain/guest_access.py` accepts a `ChallengeEvidence` receipt containing only
an opaque challenge ID and proof. It accepts no business, hotel, guest, stay or
room identifiers from the challenge payload. An injected server-side
`verify_evidence` capability validates the provider receipt, recipient, expiry,
attempt limits and replay policy, then returns a trusted `GuestSubject` resolved
from its authoritative challenge record. The authority then asks an injected
trusted resolver for current records and validates the canonical hotel
snapshot, business binding, trusted hotel mapping, one active registered stay,
and its occupant-to-room relationship through `domain/access_control.py`.
Roomay derives the guest, business, hotel, stay, and room from those records;
none is accepted as a request-body claim.

The authority creates a random opaque bearer value and stores only its SHA-256
digest with the pinned guest/stay/room scope. The token is short-lived (15
minutes), process-local, and is not self-authenticating. `revoke(token)` removes
one server-held session on logout. A verified one-time challenge is consumed
before stay lookup, so a provider outage cannot make it reusable. Guessing or
forging a token cannot create a record. Every action refreshes the hotel scope.
Expired, checked-out, unregistered, departed, changed-business, changed-stay,
or changed-room contexts fail closed and permanently revoke that process-local
session. A room move invalidates the session because WOR-12 has not supplied a
trusted move-history/audit contract.

`domain/guest_actions.py::GuestActionGateway.handle_guest_action` is the one
narrow action contract for typed chat and Vapi transcripts. The only operations
are `message`, `confirm`, and `cancel`; it delegates classification,
clarification, routing, stay verification, and request preparation to the
existing WOR-18 `handle_conversation_turn`. It accepts no arbitrary tool name,
room/stay/guest/business ID, role, reservation action, or persistence action.
AI output remains a validated suggestion and cannot grant authority. The
trusted channel adapter supplies `channel`, provider health, and any structured
classifier result; those values must never be copied from guest input or tool
arguments.

Each message includes a channel-adapter interaction ID to reconcile redelivery.
The same ID and same channel/text normally returns the same sanitized response;
reuse with different content is refused. A cached awaiting-confirmation response
is never returned with its original action handle once its proposal is no longer
active (because a newer message superseded it or it was confirmed/cancelled);
the replay instead returns a safe `confirmation_expired` status without an
actionable handle. Up to 64 distinct interactions are retained
per session; the gateway refuses additional messages rather than evicting
idempotency state. The action gateway creates a random
confirmation handle, stores the exact text and validated action context on the
server, and accepts confirmation only for that handle in that session. A new
message invalidates the pending confirmation; repeated confirmation returns a
cached response. All outputs omit `internal`, guest/stay/business identifiers,
audit data, and raw provider/server details. Results always say
`submitted=False` and `persisted=False`.

These Python checks are contracts only. A caller that can construct or replace
the injected resolver, verifier, `AccessContext`, snapshot, or session store is
inside the trusted server boundary. Python types and booleans are not a
cryptographic or Workpeg authorization mechanism.

## Future guest verification

An owner-approved production design should use one of these server-controlled
flows:

1. Resolve the guest's existing contact from an active registered stay using
   trusted Workpeg records. Send a short-lived one-time challenge only to that
   on-file phone number or email through an approved provider. Do not reveal
   which contact exists or allow the guest to replace it during verification.
2. Alternatively, issue a high-entropy, single-use invitation to the guest's
   verified on-file channel. Bind it to the exact business, hotel, guest, and
   active stay; expire it quickly and revoke it on checkout or room change.
3. Verify challenge signature/possession, intended recipient, nonce, expiry,
   attempt limits, replay, and rate limits on the server. Never accept room
   number, QR code, caller ID, a transcript, prompt text, model statement, or
   browser-supplied identity claim as the proof.
4. Resolve the active stay and registered occupant after challenge success,
   then issue a short-lived opaque session. Refresh and validate the stay and
   business scope before every hotel action.

The current hotel schema has no `hotel_id` columns. The current safe deployment
assumption is one hotel per Workpeg business unless a trusted mapping is
implemented and verified. A guest challenge may not pick a hotel or business
from user input.

## Adapter interface

The offline contract is deliberately dependency-injected:

```python
authority = GuestSessionAuthority(
    # Returns GuestSubject resolved from the server-side challenge record.
    verify_evidence=server_challenge_verifier,
    resolve_stay=trusted_workpeg_guest_stay_reader,
)
token = authority.complete_challenge(verified_evidence)
result = action_gateway.handle_guest_action(
    session_token=token,
    channel="typed_chat",  # or "vapi", set by the trusted channel adapter
    operation="message",  # fixed allowlist
    interaction_id=trusted_delivery_id,
    text=guest_text,
)
```

The example names are interface placeholders, not implemented Workpeg APIs.
For a future server, `verify_evidence` must verify a provider-signed or
otherwise trusted one-time receipt, enforce a persistent rate/attempt budget,
and return a `GuestSubject` from its server-side challenge record. The trusted
adapter must rate-limit both verification attempts and challenge issuance by a
server-derived source/recipient key; a client-selected challenge ID alone is
not a brute-force control. `resolve_stay` must read the authenticated
business and current guest/stay rows using documented, least-privilege Workpeg
capabilities, validate all row relationships, and supply a trusted
business-to-hotel mapping. The guest's token should be held in an `HttpOnly`,
`Secure`, `SameSite` cookie or equivalent protected Vapi session context; add
CSRF protection, durable revocation, and safe security logging. Do not
expose server claims or token values to model prompts.

The Vapi adapter should pass a transcript and trusted call/event ID to this same
action gateway. It must not trust caller ID or model-selected tool names. Typed
chat and Vapi must use the same session, authorization, confirmation, and
domain contracts.

## Tests and limits

`tests/test_guest_access.py` uses only the synthetic hotel fixture and mocked
challenge/stay adapters. It covers forged and replayed challenge evidence,
forged/expired session tokens, wrong business and hotel mapping, missing or
checked-out stays, departed occupants, room/stay changes, duplicate message
delivery, conflicting idempotency IDs, cross-session/forged confirmation,
prompt injection, arbitrary operations, malformed model output, provider
failure, and guest-view privacy.

No guest account, contact challenge, invitation sender, public route, production
authentication, Workpeg write, or hosted authorization was implemented or
tested by this domain contract. The standalone `apps/guest-mvp` consumes a
typed `GuestAccessAdapter`; its default adapter reports `unavailable` and makes
no network request. Until a reviewed backend is connected, the static guest
journey is a separate development-only offline preview and never establishes
authentication. The SDK and project have not verified a Workpeg guest
authentication or public Function invocation API; do not invent one. This
authority is process-local and loses sessions on restart, so it is not suitable
for multi-process production deployment.

## Requirements before real guest sessions

- Workpeg owner confirms Peg installation, business identity, guest-capable
  authentication/session primitives, and supported server-side row access.
- WOR-28/WOR-29 verifies authenticated Workpeg reads, business scoping,
  table/row permissions, guest-safe projections, and denial behavior.
- An owner-approved identity provider and verified contact challenge or secure
  invitation flow with signing, expiry, replay protection, rate limits, and
  recovery/support procedures.
- A reviewed server host or supported Workpeg server/function boundary with
  TLS, protected cookies/session storage, CSRF defense, monitoring, retention,
  revocation, and incident response.
- Trusted guest-to-active-stay mapping, single-hotel-per-business constraint
  or verified hotel mapping, checkout/room-change invalidation, and current
  occupant validation.
- A concurrency-safe idempotent service-request write, read-back reconciliation,
  audit attribution, and real staff inbox. Offline preparation alone does not
  create or notify a hotel task.
- Owner-run tests for own-stay access, other-guest and other-business denial,
  changed/expired sessions, challenge replay, unauthorized writes, and
  persistence after reload before enabling a public channel.
