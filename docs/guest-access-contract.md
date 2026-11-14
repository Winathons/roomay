# WOR-15 Guest Access Contract (Phase A)

This document describes offline, fail-closed contracts for future verified
guest chat and Vapi voice access. It is not a public guest service, Workpeg
login implementation, hosted permission policy, or proof of identity.

## Security boundary

`domain/guest_challenges.py` provides provider-neutral challenge issuance and
verification ports. `GuestChallengeService.issue` accepts a server-resolved
`GuestSubject` bound to a specific active stay and room, then resolves that
subject's on-file contact through `GuestContactResolver`; the browser cannot
choose a recipient. `ChallengeEvidence` carries only an opaque challenge ID,
proof, and a server-derived source rate key. The request adapter must construct
it from trusted ingress data and never parse the rate key from guest JSON or
untrusted forwarded headers. The provider verifies proof possession; the
challenge record supplies the identity and stay scope. No identity claims are
accepted from the proof or request body.

The service applies five attempts per challenge, three issuance attempts per
source/contact per hour, and ten verification attempts per source/contact per
15 minutes by default. The included store and limiter are bounded,
thread-safe, in-memory development/test ports. Their operations cannot enforce
limits across workers or survive a process restart. `GuestChallengeStore` and
`GuestRateLimiter` define the atomic adapter boundary; no durable adapter or
provider delivery is implemented here.

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
challenge_service = GuestChallengeService(
    provider=approved_challenge_provider,
    contact_resolver=trusted_on_file_contact_resolver,
    store=InMemoryGuestChallengeStore(),  # process-local, test only
    rate_limiter=InMemoryGuestRateLimiter(),  # process-local, test only
)
authority = GuestSessionAuthority(
    # Loads and atomically consumes identity from the challenge record.
    verify_evidence=challenge_service.verify_evidence,
    resolve_stay=trusted_workpeg_guest_stay_reader,
)
issued = challenge_service.issue(
    server_resolved_subject_with_stay_scope,
    trusted_source_key=server_derived_source_key,
)
token = authority.complete_challenge(ChallengeEvidence(
    challenge_id=issued.challenge_id,
    proof=provider_response,
    trusted_source_key=server_derived_source_key,
))
result = action_gateway.handle_guest_action(
    session_token=token,
    channel="typed_chat",  # or "vapi", set by the trusted channel adapter
    operation="message",  # fixed allowlist
    interaction_id=trusted_delivery_id,
    text=guest_text,
)
```

The example provider and Workpeg names are interface placeholders, not
implemented APIs. A production deployment needs provider-signed or otherwise
trusted one-time proof, atomic durable challenge consumption, shared persistent
rate limits and attempts, and a session store with durable revocation. Its
trusted source key must be derived from a verified ingress/proxy configuration;
the contact resolver must use an existing verified on-file contact.
`resolve_stay` must read current guest/stay rows using an approved
least-privilege capability, validate all row relationships, and supply the
trusted business-to-hotel mapping. The guest token should be held in an
`HttpOnly`, `Secure`, `SameSite` cookie or equivalent protected Vapi context
with CSRF protection and safe security logging. Never expose server claims or
token values to model prompts.

The Vapi adapter should pass a transcript and trusted call/event ID to this same
action gateway. It must not trust caller ID or model-selected tool names. Typed
chat and Vapi must use the same session, authorization, confirmation, and
domain contracts.

## Tests and limits

`tests/test_guest_challenges.py` and `tests/test_guest_access.py` use synthetic
subjects and a fake provider. They cover on-file contact resolution, source and
recipient rate limits, bounded proof attempts, expiry, replay, provider outage,
concurrent verification, challenge-bound stay/room, wrong business/hotel/guest
scope, session expiry/revocation, checkout and room changes, and fail-closed
stay-reader errors. There is no restart-recovery test because the included
challenge store, limiter, session state, and revocation state are process-local.

No real contact challenge, public route, production authentication, Workpeg
write, or hosted authorization was implemented or tested. The standalone
`apps/guest-mvp` consumes a typed `GuestAccessAdapter`; its default adapter
reports `unavailable` and makes no network request. Until a reviewed backend is
connected, the static guest journey is a separate development-only offline
preview and never establishes authentication. Current Workpeg capability
inspection and the installed-SDK record show no approved guest authentication
or public Function invocation API; do not invent one. The in-memory ports are
not suitable for multi-process production deployment.

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
