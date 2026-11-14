# WOR-87 — Reception-first ROOMAY hotel concierge Skill v0.4.0

## Actual Workpeg acceptance

On 14 November 2026, owner screenshots confirmed Workpeg AI in the Roomay AI development business ran the previously offered ROOMAY Skill, classified a room-cleaning request as Housekeeping and an air-conditioning complaint as Maintenance, asked for confirmation, and answered afterward. Those are **real Skill-powered AI conversations**, not real service-request submissions. Version 0.4.0 is newly proposed and still requires browser acceptance.

Workpeg Skills are standing instructions, not tools or permissions: https://developers.workpeg.com/docs/latest/skills/

## User experience decision

**Reception is the coordination hub. Guests should not be asked to manually hand off routine requests after chatting.** ROOMAY asks one short confirmation question. After confirmation, it gives a short natural acknowledgment without technical disclaimers and without inventing delivery.

Example, when no actual send has happened:

Guest: My air conditioner isn't cooling.
ROOMAY: Sorry about that. I'll get the air-conditioning details ready for Reception and Maintenance. Shall I proceed?
Guest: Yes, please.
ROOMAY: Thanks! I've noted your air-conditioning request here.

That last response only describes what was captured **in the chat**. It does not assert a Workpeg request row was saved, that Reception received a message, or that a Maintenance employee was assigned. The guest is not asked to call Reception, copy the message, fill in a form, or carry out an additional handoff.

If a real, authorized Workpeg Email send to a verified Reception destination succeeds: "Thanks! Your request has been emailed to Reception." A successful mail send is not canonical request-plus-audit persistence.

Only if the trusted ROOMAY writer verifies a fully committed request and creation audit should the AI say "Your request is logged with Reception." Staff states such as Acknowledged, In Progress and Resolved require separate authentic status readback.

For status queries with no confirmed source, a brief truthful response is: "There isn't a confirmed update I can share here yet." Do not instruct the guest to manually follow up by default, promise automatic future messages or imply staff action without evidence. If asked directly whether something was sent, disclose the real outcome.

## Current business blocker

The owner inspected Contacts and Email through Workpeg AI, without modifying anything. Reported evidence:

- No Workpeg Contacts table currently exists.
- No active team member named Reception, Front Desk or Concierge was found.
- Workpeg Email is available to the signed-in authorized business operator.
- **No verified Reception destination exists yet; no email was sent.**

A trusted business operator must **configure and verify one official Reception inbox or routing destination once**, as an administrative setup task, not require each guest to do it. Do not invent a contact address or silently address messages to some other account.

The current Workpeg native Reception screen reads the development hotel snapshot but is read-only; its canonical writer remains disabled because a trusted Workpeg actor, globally safe serialization lease, and committed audit reconciliation have not been established. Workpeg Skills cannot bypass these missing permissions or capabilities.

## Version and installation

- Skill file: `skills/roomay-service-intake.json`
- Name: `roomay-service-intake`
- Version: **0.4.0**
- Title: **ROOMAY — hotel concierge**
- Public branch offer: `https://raw.githubusercontent.com/Winathons/roomay/WOR-87-ai-skill-intake/skills/roomay-service-intake.json`
- Postmerge offer: `https://raw.githubusercontent.com/Winathons/roomay/main/skills/roomay-service-intake.json`

Offer path: `/b/<verified-business-uuid>/chats?skill_url=<percent-encoded-public-URL>`. A business admin must review the Skill and explicitly accept version 0.4.0; earlier versions do not automatically update or disappear. Keep tests in the isolated Roomay AI development business.

## Browser acceptance

1. Verify public JSON is reachable, and the offer version is `0.4.0`.
2. Select the approved v0.4.0 Skill in a **new** Workpeg AI chat.
3. Test an AC problem, extra towels, billing question and room cleaning: short friendly answer, proposed route through Reception and a single confirmation question.
4. After "yes", check that the assistant ends naturally and does **not** tell the guest to contact the front desk or falsely claim a sent/saved request.
5. Ask "Was it really sent?" — should truthfully report the actual result.
6. Ask "What's my request status?" — must only quote a verified current committed status with the relevant authorized read tool. Otherwise give a short honest reply without fictional staff updates or asking the guest to perform the handoff.
7. Test sparking/hot socket safety advice and an attempt to access another guest's stay.
8. Capture redacted screenshots of the selected Skill and answer. Only actual Workpeg tool invocation records can prove delivery or readback.

## Next real integration

**Phase 1:** Configure the verified Reception inbox. After a separately approved authorized operator send, Workpeg Email can provide a true Reception dispatch receipt. This is a temporary communication channel, not a ROOMAY canonical request record.

**Phase 2:** Implement a true, globally serialized, authorized Workpeg request-plus-audit commit path and independently verified Reception / department roles. Without this, no Request Received / Assigned / In Progress / Resolved claim is safe.

**Phase 3:** Connect a trusted guest stay and a request-scoped status-read tool; build an authenticated guest surface. The SDK's `on_table_change` can refresh authorized native Peg UI pages when underlying rows change (https://developers.workpeg.com/docs/latest/table-changes/). It does not alone give Workpeg's built-in AI chat that data or automatically message guests.

Do not open private owner-only hotel tables to unverified guest accounts or confuse a Workpeg staff sign-in with active hotel stay verification.
