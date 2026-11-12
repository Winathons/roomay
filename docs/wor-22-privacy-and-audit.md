# WOR-22 — Staff authorization, guest privacy and auditable operations

**Status:** Offline policy and regression slice. This document does not authorize
production records, Workpeg permission changes, public guest access or live AI
actions. The owner-only Workpeg table policy `700` remains unchanged.

## Trusted authority boundaries

The release-facing `ui/hotel_data.py` uses authenticated Workpeg UI
table helpers for a **read-only** Reception view. The standalone FastAPI and
PostgreSQL prototype was **merged into main as inactive infrastructure**
([PR #37](https://github.com/Winathons/roomay/pull/37)); its normal ASGI
entrypoint refuses startup, the unsupported external developer-`WORKPEG_PK`
reader was removed, and the default hotel-data reader returns sanitized 503.
A deliberate `ROOMAY_ENABLE_STANDALONE_PROTOTYPE=local-only` setting is
for isolated development only. Real staff OIDC registration and the supported
external Workpeg access path remain unverified.

The owner approved **Workpeg Tables as the sole authoritative operational
service-request/audit store** in
[WOR-62](wor-62-pr37-source-of-truth.md). The PostgreSQL prototype's
request/audit records are not synchronized with Workpeg Reception and must
never be described as received by actual hotel staff. Hosted vendor
acceptance is consolidated in
[WOR-69](https://linear.app/workpeg/issue/WOR-69).

The `domain/access_control.py` `AccessContext` and
`domain/staff_actions.py` ports are **pure, offline contracts**, not tokens,
real Workpeg permission grants, or proof of any actor. A trusted integration
must derive actor, business, member role, hotel mapping, department and
revocation state from the vendor-supported staff session and a reviewed
directory. Never accept browser-supplied `role`, `guest_id`,
`business_id`, `verified`, QR text, room number or AI output as authority.

A `200` read from a browser development route is not proof that a different
staff role can read it. A release must fail closed while the owner-only 700
table grants or multi-role behavior remain unverified; do not broaden table
permissions to make the UI appear operational.

## Permission matrix — tests and required enforcement

| Action or data | Owner/manager | Reception | Housekeeping | Maintenance | Guest |
| --- | --- | --- | --- | --- | --- |
| Guest identity/booking contacts | Per approved role | Reception duties only | Denied | Denied | Own verified stay only |
| Confirm reservation / check-in/out | Trusted verified write only | Trusted verified write only | Denied | Denied | Denied |
| Room cleaning and readiness | Authorized operation | View status | Update only authorized cleaning work | Denied | Denied |
| Maintenance block release | Authorized verified action | View only | Denied | Authorized assigned maintenance role | Denied |
| Department ticket | Supervision | Triage and route | Housekeeping only | Maintenance only | Create/read own verified stay only |
| Read audit history | Authorized owner/manager | Denied | Denied | Denied | Denied |
| Staff membership/permission configuration | Workpeg owner-approved process | Denied | Denied | Denied | Denied |

All high-impact writes additionally require verified business/hotel/stay
binding, actor and time, serialization/retry safeguards, committed audit and
read-after-write or reconciliation. Pure Python permission approval is **not**
an authorized Workpeg writer.

The receptionist request projection now keeps references and task fields
needed for operational follow-up, but withholds internal
`idempotency_key`, `last_event_id`, and
`last_operation_signature`. Department projections already omit stay, guest,
hotel and audit-linkage identifiers. Managers/owners retain the canonical
record only behind a separately verified privileged role.

The `description` field is **free text** and might include names, contact
details, health or payment information. Field omission does not redact such
text; restrict visibility to legitimate operational staff and define
retention/access logs before real guests. A screen hiding a field does not
restrict direct API/table access.

## Privacy notice and human assistance — proposed wording, NOT published

> ROOMAY uses information about your verified hotel stay and the help requests
> you submit to route those requests to authorized hotel staff and show you
> their progress. Room and stay identity must be verified privately; entering
> a room number or scanning a room QR code is not verification. Authorized
> departments receive only the details required to handle your request.
>
> ROOMAY may use speech-to-text, AI services and text processing when you
> choose an available conversational channel. Your words may be processed by
> approved service providers for interpreting and responding to your request.
> This service does not confirm a booking, dispatch staff, or record a completed
> request until the authorized hotel system confirms the action. If a channel
> is unavailable, speak with hotel reception directly.

**Owner decisions required before publishing this notice:** exact providers,
whether audio/transcripts are stored, retention and deletion duration per
data class, AI processing consent/legal basis, subprocessors and cross-border
transfer review, access monitoring, data subject contact/rights, emergency
escalation phone number, and country-specific review. Do not invent a retention
period or imply voice services are live. Minimize logs and remove secrets and
guest text from failure diagnostics. An emergency or transfer promise needs an
actual monitored human contact path.

## Offline regression checks

`tests/test_wor22_security.py` adds deterministic checks for:
- Role-by-resource authorizations and denied high-impact staff/guest actions.
- Nonmember/unverified session claims and other-business/hotel isolation.
- Receptionist/dept/guest request field minimization, sensitive ticket denial
  and own-active-stay checks.
- Strict audit validity: a pending, malformed or tampered audit entry is not
  accepted as a committed operation.
- Fixed safe errors without arbitrary private content.

Also retain prior coverage in `tests/test_access_control.py`,
`tests/test_staff_actions.py`, and `tests/test_service_requests.py`.
CI exercises synthetic roles and mocked data; this is not a production
authorization attestation.

## Actual acceptance still blocked

1. **WOR-69:** The vendor-supported external guest/Vapi → Workpeg
   Function or Tables invocation, registered staff OIDC client/callback and
   replay-safe canonical request/audit writer are not yet verified. Workpeg
   membership claims are not a standalone Tables credential. WOR-61/62
   completed **investigation and design phases** only.
2. **WOR-28/29:** The owner previously verified an authenticated owner read
   of the fictional hotel snapshot and a separate ordinary Member's
   table-list result `200 []` under owner-only `700` rights. That is
   **limited, positive denial evidence**, *not* proof of all direct-table,
   role, cross-business or hosted write permission paths. Remaining
   authorization and supported native write tests must be performed with
   authorized sessions without broadening permissions as a shortcut.
3. **WOR-11/12/13/20 and WOR-14/65:** Workpeg-native hotel actions still
   require an actual trusted writer with serialization/idempotency and a
   committed actor/time audit followed by independent-session readback.
   Existing offline `persisted=False` plans never constitute booking,
   checkout, maintenance clearance or staff request delivery.
4. **Privacy review:** The owner must approve actual data processors, speech
   and text storage/retention, guest notice and lawful handling before any
   live calls/transcripts or public deployment.

**Completion boundary:** the **offline** policy, least-privilege projections,
negative regressions and proposed privacy notice are already delivered.
WOR-22's **hosted acceptance remains Backlog** until authenticated Workpeg
staff rights, committed audit integrity, separate-role denial and the
owner-reviewed privacy behavior can be verified. Keep the live gates under
WOR-28/29/69 and the appropriate staff workflow implementation issues;
offline CI does not authorize a deployment or mark hosted verification complete.
