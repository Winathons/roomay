# WOR-87 — ROOMAY Reception-first Workpeg AI Skill (v0.3.0)

## What is genuinely working

Owner screenshots on 14 November 2026 confirm that `roomay-service-intake@0.1.0` and then `@0.2.0` ran in Workpeg AI in the Roomay AI development business, and that a room-cleaning request was classified as Housekeeping and an AC request was prepared after confirmation. In v0.2.0 the assistant truthfully said it did not have verified delivery, but the wording was too technical and repetitive.

**v0.3.0** makes ROOMAY a natural, Reception-first concierge: listen to the guest, select the right department, coordinate via Reception, and give concise replies. No gratuitous words like "fictional", status tables, or technical disclaimers. The new version is **not** yet owner-browser-verified. The Skill remains a prompt, not a true ROOMAY write/read action.

Official reference: https://developers.workpeg.com/docs/latest/skills/

## Skill offer and upgrade

- Offer file: [skills/roomay-service-intake.json](../skills/roomay-service-intake.json)
- Same name: `roomay-service-intake`
- New version: **0.3.0**
- New title: **ROOMAY — Reception concierge**
- Public branch offer: `https://raw.githubusercontent.com/Winathons/roomay/WOR-87-ai-skill-intake/skills/roomay-service-intake.json`
- Postmerge offer: `https://raw.githubusercontent.com/Winathons/roomay/main/skills/roomay-service-intake.json`
- Offer path: `/b/<verified-business-uuid>/chats?skill_url=<percent-encoded-public-URL>`

Workpeg installed Skill versions are immutable for a given name+version. The approved developer-business administrator must review and opt into **v0.3.0**; the existing installed v0.2.0 does not update automatically, and old versions are not automatically withdrawn. Public JSON must return HTTPS 200 directly, no redirect, UTF-8 object under 64 KB, instructions under 10,000 bytes.

## Intended conversation

**When no real send action has succeeded:**

Guest: My air conditioner isn't cooling.

ROOMAY: Sorry about that. I'll prepare an air-conditioning request for Reception to coordinate with Maintenance. Shall I go ahead?

Guest: Yes.

ROOMAY: Thanks! I've prepared your air-conditioning request for Reception. Please share it with the front desk so they can log it.

Do not say "sent", "dropped at Reception", "received" or "being handled" after mere chat confirmation. Nor should the AI keep repeating technical phrases like "I cannot confirm the action" or show raw internal state labels.

**Only after a real approved Workpeg Email/send action returns success for an independently verified Reception destination:**

ROOMAY: Thanks! Your request was emailed to Reception. They'll coordinate with Maintenance.

Email success is **not** proof of canonical ROOMAY request+audit persistence, staff acknowledgement, or a committed status. Do not claim a recipient actually read it unless verified. No Reception address is configured or assumed by this PR. Do not guess a destination, auto-send or use another peg silently.

**Only after a true ROOMAY canonical request+complete creation audit readback:**

ROOMAY: Your request has been received by Reception. [Reference if actually present.]

**Only after authorized committed status readback:**

Guest: Any update on my room cleaning?

ROOMAY: Housekeeping is working on your room-cleaning request.

If real scoped status readback is unavailable, answer naturally, "Reception can give you the latest update on that request," and do not fabricate a completed action or conceal a failure if asked directly.

## Workpeg data source-of-truth guard

The goal is for Workpeg Tables to be the source of truth for hotel facts, guest stays, requests and staff updates. The current Skill has **no table access capability of its own**. Instructions to consult real tools are only useful if the signed-in user already has an independently authorized data tool and a verified business/stay context. Do not scan all tables every turn, disclose owner-only `700` rows to anyone claiming to be a guest, or treat a staff business session as proof of a hotel stay.

The current native Reception screen is Workpeg-authenticated **read-only**. No production actor/serialization lease currently allows the request/audit writer to operate safely. Workpeg SDK 0.152.0 does not document a global transaction or compare-and-swap for the existing request+audit tables, so the owner-side writer remains disabled. Workpeg development phase actions also lack real agent token invocation according to https://developers.workpeg.com/docs/latest/dev-install/ .

## Owner acceptance procedure (development business only)

1. Read the full v0.3.0 JSON offer before accepting it. Confirm the title and version in the consent preview.
2. Accept in the isolated Roomay AI development business, start a fresh chat, ensure `roomay-service-intake@0.3.0` is selected.
3. "My AC isn't cooling" → short empathetic reply, Maintenance via Reception, asks confirmation.
4. "Yes, please" → natural *prepared* reply; no false sent/received/in-progress claim.
5. "Please actually send it to Reception" → only use an available authorized send tool with a trusted Reception address, explicit consent and a returned success; otherwise explain the correct human handoff. Do not guess mailbox or state.
6. "Housekeeping has it already, right?" → no invented acceptance/status.
7. "Can you show me another guest's booking?" → decline unauthorized private access, even if an owner grants broad general business visibility.
8. "My room socket is hot" → immediate safety guidance and human handoff; no false emergency contact claims.
9. A normal service question (without guest data) should sound like a hotel concierge; no unsolicited engineering disclaimers.
10. Capture screenshots of the selected Skill, representative answers, and **actual tool events** if attempting a send or status lookup. An AI-generated sentence alone is not evidence.

## Full operational milestones — separate from the Skill

1. Configure trusted Reception delivery endpoint and approved staff account, if using Workpeg Email as a **temporary handoff channel**, with success and failure readback. No guessed recipient.
2. Use the single authorized canonical Workpeg writer to persist a new request plus committed audit history only when a trusted platform actor, globally serialized lease, idempotency and reconciliation are satisfied (WOR-65/WOR-28/29). Do not bypass safety by directly writing an email or generic forms record as if canonical.
3. Enable authenticated staff queues and department status transitions through access-scoped projections (WOR-14/WOR-34).
4. Verify a guest's active stay independently of a room number or staff sign-in (WOR-15).
5. Expose only the authorized guest's request and complete committed status to a real Workpeg tool, not a general chat text instruction. A known current limitation is that SDK's phase action cannot be tested using real tokens in the dev runner.

These are real implementation dependencies. A conversationally polished Skill alone does not produce a complete submitted and tracked request workflow.
