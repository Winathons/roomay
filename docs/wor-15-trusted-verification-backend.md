# WOR-15 — Trusted guest verification components

**Status:** Offline, provider-neutral preparation only. No guest endpoint,
contact delivery, Workpeg API call, hosted identity, operational rate limit, or
durable session has been enabled.

## Components

- `domain/guest_challenges.py` defines `GuestChallengeProvider`,
  `GuestContactResolver`, `GuestChallengeStore`, and `GuestRateLimiter` ports.
  `GuestChallengeService` issues a random challenge ID to an on-file contact
  resolved for a trusted `GuestSubject`, then verifies proof using the provider.
  Identity and stay scope are read from the server-side challenge record; the
  provider returns only a proof-validity result.
- Each challenge binds business, hotel, guest, stay, and room. The
  `GuestSessionAuthority` consumes it before stay lookup, rejects a changed
  stay/room, and verifies the current active registered occupant before issuing
  its 15-minute opaque session. Only the session token digest is retained.
- `domain/access_control.py` remains the policy boundary for business/hotel,
  guest, active stay, occupant, and room relationships. `GuestActionGateway`
  still revalidates the latest stay before every protected action.
- `InMemoryGuestChallengeStore` and `InMemoryGuestRateLimiter` are explicitly
  development/test implementations. Their atomic operations serialize threads
  in one process and their state is bounded. Default limits are five proof
  attempts per challenge, three issuance attempts per source/contact per hour,
  and ten verification attempts per source/contact per 15 minutes.

The trusted web adapter must construct `ChallengeEvidence` itself. It may add
only a source key derived from trusted ingress; never accept that value from a
guest body or an untrusted forwarding header. `GuestContactResolver` must
select an existing contact for the challenge-bound guest/stay and must not
accept a replacement recipient from the guest. Provider delivery and provider
proof policy remain explicit interfaces; no provider has been selected or
implemented.

## Concurrency and storage boundary

`GuestChallengeStore.begin_attempt` and `consume` must be atomic compare-and-set
operations. `consume` has one successful winner even if two valid provider
responses race. A future multi-worker adapter must provide the same guarantees
across processes and restarts. `GuestRateLimiter` must likewise be shared and
persistent. Store only security state, protect private subject/contact-binding
metadata at rest, never store challenge proof, and never copy hotel requests,
stays, or other operational rows into a separate database.

The current implementations are in memory. Restart loses pending challenges,
attempt counters, rate-limit windows, sessions, and revocation state. No
restart recovery or cross-process correctness is claimed or tested. If durable
storage is approved, implement the ports in the already approved security
boundary or in a narrowly scoped security-state store; do not create a second
hotel operational source of truth.

## WorkPeg and guest-authentication blockers

Workpeg OIDC and `WorkpegAuth` verify registered relying-party identities and
selected business membership for staff. They do not prove guest identity or an
active hotel stay. The current SDK/docs do not establish a public guest
challenge/session API, authenticated browser-to-Function invocation, or a
least-privilege guest reader for the owner-only hotel tables. No SDK dependency
was available in this offline test environment, so this phase uses only the
recorded SDK 0.152.0/source and current documentation findings in
[`wor-69-integration-audit.md`](wor-69-integration-audit.md),
[`wor-15-guest-access-phase-b.md`](wor-15-guest-access-phase-b.md), and
[`wor-61-auth-boundary.md`](wor-61-auth-boundary.md). It does not assume staff
OIDC is guest authentication.

Before live guest verification, Roomay needs all of the following:

1. Owner/vendor-approved guest challenge or invitation delivery, including
   verified on-file contact lookup, proof binding, expiry, single-use/replay
   semantics, and recovery/support policy.
2. A supported server invocation and Workpeg data-read boundary with documented
   authentication, business scoping, least privilege, safe projections, and
   explicit denial behavior. `WORKPEG_PK`, staff OIDC tokens, and invocation
   tokens are not substitutes.
3. A verified business-to-hotel mapping and an active-stay/registered-occupant
   reader that can revalidate checkout, occupant departure, and room transfer
   against current canonical Workpeg records.
4. An approved HTTPS server/ingress, trusted source identity, secure session
   cookie or equivalent Vapi context, CSRF defense for browser flows, shared
   durable challenge/session/revocation/rate-limit storage, protected secrets,
   redacted security logs, and operational recovery procedures.
5. Owner-run concurrent, restart, own-stay/other-guest, cross-business, expired,
   revoked, checkout, room-change, provider-outage, and hosted denial tests
   against the selected provider and actual authorized Workpeg path.

The UI from merged PR #88 remains the fail-closed client and is not modified.
The dormant PostgreSQL prototype is not activated and does not become a second
request/audit writer. Reception UI paths, `apps/guest-mvp`, and `apps/web` are
outside this change.

## Offline validation

```bash
python -m unittest tests.test_guest_challenges tests.test_guest_access -v
python -m compileall -q domain tests
```

These tests use synthetic stay snapshots and fake challenge ports. They prove
only the in-process contracts described above, not contact delivery, Workpeg
authorization, durable rate limits, persistence, or hosted guest access.
