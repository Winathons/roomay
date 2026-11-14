# WOR-77 — Provider-neutral guest MVP contracts

**Status:** Offline contract preparation only. This document and the schema do not add an endpoint, Workpeg action, AI provider call, hosted write, or authentication mechanism.

The wire contract is versioned as `roomay.guest-mvp.v1` in [`contracts/roomay.guest-mvp.v1.schema.json`](contracts/roomay.guest-mvp.v1.schema.json). It uses JSON Schema Draft 2020-12, strict objects (`additionalProperties: false`), and one typed envelope per message. Consumers must reject an unknown contract version or message type instead of guessing. The schema describes safe projections and outcomes; it is not evidence that a caller is authenticated or authorized.

## Consumer flow

1. A trusted adapter resolves a verified guest context from an authenticated challenge/session and a fresh hotel snapshot. `guest_context` may expose only approved hotel facts and the guest's verified room display label. Never accept guest, business, hotel, stay, or room identity from a prompt or browser payload.
2. The guest UI submits `conversation_action` with `message`, `confirm`, or `cancel`. WorkPeg AI may propose text, intent, category, and department, but its output is untrusted. Validate it with `domain/conversation_intake.py`; derive identity, room, category routing, and confirmation authority through trusted server/domain context. A `request_draft` is a preview and always requires a separate explicit confirmation handle.
3. On confirmation, call the existing canonical `domain.service_requests.create_request` planner. Only a separately authorized writer may persist its request and audit event. Return `request_outcome` with `persisted: true` only after durable request-and-audit readback. A timeout or partial write is `uncertain`; reconcile using the existing writer contract before retrying. An exact replay is `duplicate`, while reused keys with different content are a conflict.
4. The native receptionist adapter maps authorized dashboard actions to `reception_transition`, checks the expected version and current request, then delegates permissions and legal transitions to `domain.staff_actions.StaffActionGateway` and `domain.service_requests.transition_request`. The schema does not grant a role or permit a transition.
5. Guest status readback resolves the current guest session and own active stay again, then returns only `request_reference`, status, update time, and an approved short guest message. Do not return internal guest/business/stay/room IDs, staff-only notes, or audit events. Wrong guest/business/room and revoked/expired stay responses are indistinguishable where exposing a difference could disclose records.

## Existing domain contracts to reuse

| Versioned message | Existing implementation |
| --- | --- |
| Verified guest/stay context | `domain.guest_access.GuestSessionAuthority`, `ResolvedGuestStay`, and `domain.access_control` |
| Authorized hotel/room information | `domain.hotel_facts` and `domain.access_control.project_guest_view`; only configured, reviewed sources may be returned |
| AI conversation actions | `domain.guest_actions.GuestActionGateway` and `domain.conversation_intake.handle_conversation_turn` |
| Request draft and explicit confirmation | Guest action confirmation handle plus `domain.service_requests.create_request` |
| Canonical request and audit | `domain.service_requests` request plans and `reconcile_write`; `domain.workpeg_writer.NativeRequestWriter` is disabled by default and not constructed by production code |
| Reception transitions | `domain.staff_actions.StaffActionGateway`, `transition_request`, and persistence reconciliation |
| Guest status readback | Existing guest projection policy in `domain.access_control`; a verified read adapter is still required |

This schema is the transport contract, not a parallel request/status model or source of truth. Canonical request fields, status rules, routing and audit sequence remain owned by `domain.service_requests`; schema values must be mapped and checked against that module. No Workpeg table or schema changes are included.

## Failure and persistence semantics

`failure_code` makes unauthenticated access, unverified membership, wrong business/hotel/room, revoked or expired stay, duplicate or conflicting operation, unavailable Workpeg service, uncertain persistence, stale version, and forbidden/not-found results explicit. Public adapters must map internal errors to these fixed codes and safe messages; never return exception or SDK error text.

`request_outcome.state` distinguishes `created`, `duplicate`, `rejected`, `unavailable`, and `uncertain`. `persisted` is true only when the canonical request and its audit event have both been confirmed durable. Do not turn a timeout into a failed or successful write claim, and do not retry an uncertain operation with a new idempotency key. `request_reference` and `audit_reference` are returned only when their status is known and the recipient is authorized.

## Platform dependencies and non-goals

WorkPeg has not yet supplied a verified guest-capable session, an approved trusted guest adapter, guest-safe row projections, or least-privilege service-request/audit permissions. The owner-only table permissions, missing verified multi-hotel/business mapping, external guest-to-Function invocation boundary, Workpeg AI context binding, supported durable idempotency/serialization, and hosted request/audit readback remain platform/owner acceptance dependencies documented in WOR-28/29, WOR-61/62, and WOR-64. The currently disabled native writer must not be enabled by this contract.

No public endpoint, Workpeg SDK API, hosted AI action, service deployment, secret, live data read, or Workpeg write is defined here. Those require separately verified platform behavior and owner acceptance. The schema's generic hotel information values must come from an approved source allowlist; existing `domain.hotel_facts` intentionally has no live Workpeg source mapping.

## Validation

Run `python -m unittest tests.test_guest_mvp_contract_v1 -v` for deterministic version, message-shape, authorization projection, explicit-confirmation, and failure-state checks. The tests use only the checked-in schema and standard library; they do not perform authentication or provider calls.
