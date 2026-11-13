> Design audit history for Roomay (WOR-7). It started on the stand-alone prototype, which is now `apps/web`.

# Roomay design audit — issue by issue, plus AI-tell review

**Audited:** the localhost prototype as of Nov 10, 2026, against every Linear issue assigned to Abdul (WOR-7 and WOR-24, WOR-35 to WOR-46) and the project lead's review comments on WOR-37, WOR-52 and WOR-47.
**Method:** each issue's acceptance criteria were read line by line and checked against the running build. Patterns were checked against Mews' published Timeline and Smart detail documentation. AI tells were checked against published catalogs of AI-generated UI. Sources are at the end.

Scale: **Exceeds** · **Meets** · **Partial** · **Missing** · **⚠ Violates** (contradicts an explicit requirement)

---

## 1. Lead's review comments (highest priority — they gate acceptance)

| Lead requirement (WOR-37 / WOR-52 / WOR-47 comments) | Before this pass | Status |
|---|---|---|
| Never show success-coloured "live records" unless a validated snapshot loaded; show the data source neutrally | Sidebar showed a **green pulsing "Live · Workpeg"** on synthetic data | ⚠ Violates (P0) |
| Today = KPI summary first; **8 KPI** hierarchy; arrivals, departures, overdue | 5 KPIs; arrivals and departures present; overdue present | Partial |
| Occupancy vs housekeeping vs maintenance as separate states, with a legend | Separate on tiles; legend mixed derived and primary keys | Meets |
| Designs at **1366 / 768 / 390** | Checked at 1440 and 1100 only; 768 and 390 reception not designed | Partial |
| 400 / 401 / 403 / loading / empty / no-match states, including the real `403 dev-origin-refused` | Only a no-match filter state in the prototype; the rest existed only in the older Figma frames | Missing |
| Mobile cards use full width; compact header | Not designed for reception mobile | Missing |
| Selected filter, focus and 44px targets | Focus ring and selected segment exist; touch sizes not verified | Partial |
| `In house` = active stays; `Needs cleaning` = every non-ready room | `Needs cleaning` counted dirty only | Partial |

## 2. Issue-by-issue coverage

| Issue | What it asks | Before this pass | Status |
|---|---|---|---|
| **WOR-7** Design lead parent | Figma pages, journeys, components, labels, Linear links, review of compiled UI | Figma exists but has **drifted** from the prototype (different teal, fonts, components). Nothing linked in Linear yet. | Partial |
| **WOR-35** Roles and IA | ≤5 reception nav items, staff, guest and manager maps, end-to-end flow, walk-in, room change, cancellation, lost connectivity | Product map in Figma. Prototype has 4 of 5 nav items (no **Guests**). Room change, cancellation and connectivity flows missing. | Partial |
| **WOR-36** Visual identity and components | Tokens, components with every state, 1440/1280/768/390/360 baselines, Workpeg-feasible | Tokens and components exist, but **the visual language reads AI-generated** (section 3). No stale, unauthorized or offline component states in the build. | Partial |
| **WOR-37** Today and room board | Live-feeling Today; separate states; filters; room detail; guided actions; edge cases (zero rooms, all dirty, overdue, 401/403/400, timeout, unknown write) | Strong Today, board, timeline and inspector. **P0 provenance violation**, no error or auth states, no tablet or mobile. | Partial ⚠ |
| **WOR-38** Walk-in, check-in, room change, checkout | Booking and **check-in as separate transitions**, occupants, rate and payment status, read-back, **≥6 refusal cases**, change room with reason, checkout failure handling | Walk-in **books and checks in in one step** (contradicts the brief). No occupants, no read-back, **no change-room flow**, about 2 refusal cases. | ⚠ Violates / Partial |
| **WOR-39** Reservations desk | Filters (source, status, dates, type, unassigned); detail with audit, rate, notes; **concurrency conflict**; cancel with reason; edit; duplicate, unknown and offline states | Pending review with ranked rooms is strong. No filters, cancel, conflict, audit trail or failure states. | Partial |
| **WOR-40** Department inbox | Mobile My Tasks and **detail**; state machine incl. Assigned, Reopened, Cancelled, Escalated; housekeeping **inspection**; maintenance **block → authorized unblock**; reception triage; offline and race states | List with one-tap progression. No detail screen, no inspection step, no block or release path, partial state machine. | Partial |
| **WOR-41** Guest booking request | Public mobile: catalogue, dates and guests, provisional vs confirmed, request form with consent, reference, no instant-booking promises | Not built | Missing |
| **WOR-42** My Stay and QR | QR landing with **no guest data until verified** via a short-lived invitation; requests; ticket ref only after save; expired, checked-out and revoked states | Verification used **last 4 phone digits**, which the issue explicitly says is not authentication. Request and tracking otherwise good. | ⚠ Violates / Partial |
| **WOR-43** Conversation, voice, WhatsApp, handoff | Confirm before ticket; voice permission, transcript edit and failure states; WhatsApp storyboard marked *future*; sensitive intents go to a human | Confirm-before-send and human handoff are good. Voice has no permission or edit states. No WhatsApp storyboard, no sensitive-intent routing. | Partial |
| **WOR-44** Manager and setup (P2) | Setup empty state, roles matrix, overview, incident response | Not built | Missing (P2) |
| **WOR-45** Accessibility and truthful states | 360–1440 widths, AA contrast, focus, reduced motion, honest terms, PII by role, test with **two people** | Contrast AA held; reduced motion respected; widths partial; usability test not done | Partial (testing blocked until testers are available) |
| **WOR-46** Handoff | Figma, token sheet, screen → route → data → permission mapping, **copy deck**, implementation review | Handoff page in Figma (outdated). No copy deck. | Partial |
| **WOR-24** Onboarding and help | First-run hints for receptionist and staff, help microcopy, printable quick start | Not built | Missing |

### Where we're already doing well, or better than asked
- **Live cross-role follow-through.** A guest request updates housekeeping and the front desk instantly. No issue asked for this level of proof.
- **Roomay Assurance** ranks eligible rooms and **explains each exclusion** (blocked, occupied, overlapping). This goes beyond WOR-39 and WOR-38.
- **Arrival-risk catch:** a dirty room assigned to an arriving guest gets a one-click reassignment. This is the brief's "avoid assigning unsuitable rooms" made concrete.
- **Undo on every write**, a command menu and keyboard shortcuts. These speed up experienced receptionists without slowing new ones.
- **Truthful copy around payments** ("Roomay doesn't process payments") and **pending vs confirmed** wording.

## 3. AI-tell review

A design that "looks AI-made" costs trust with judges and hotel buyers. These tells were found in the current build; every one is fixed in this pass.

| Tell (from published catalogs) | Where it appeared | Fix |
|---|---|---|
| "Tasteful" second-order default: **cream canvas + serif display** ("the Claude look") | Warm stone background, Instrument Serif greetings | Neutral light-grey canvas; **Century Gothic** headings (per your direction); IBM Plex Sans body |
| "Tasteful free font set": **Geist, Instrument Serif** | Whole UI | IBM Plex Sans and Mono for UI; Century Gothic (Questrial fallback) for headings |
| **Sparkle icon standing in for AI** | "Roomay noticed", "Best match", topbar sparkle | Removed. Suggestions appear inline where the decision is made, labelled plainly. |
| **Icon in a rounded square** | `ico-slot` on every list row, KPI and request | Removed; plain 16px icons only where they carry meaning |
| **Tracked uppercase eyebrows** and **"A · B · C" meta strings** | "TUE 10 NOV · FRONT DESK · MORNING SHIFT"; captions full of middots | Sentence case; data in table columns, not run-on strings |
| **Pulsing / animated status dot** | "Live" pulse | Static, neutral **data-source** label (also fixes the lead's P0) |
| **Same fade-up on every element** | `rise` animation on every card | Removed; motion only for panels and sheets (enter/exit), 150–240ms |
| **Arrows on CTAs** | "Review →", "Open board →", "All arrivals →" | Plain verbs |
| **Mini landing pages** ("One list. The right room first.", "Hospitality that follows through.") | Staff, guest and live views | Removed; those views now show only screens and flows |
| **Chatty, cute microcopy and em-dash heavy copy** | "Good morning, Amaka.", "All done. Lovely.", "All done — enjoy!" | Plain operational English, hotel tone, Nigerian-friendly, ready to localise |
| **Gradient hero with decorative stripes** | Guest app header | Solid surfaces with real content; photo placeholder only in the public catalogue |
| `shadow + border + rounded-12` on everything | Cards, tiles, KPIs | Hairline borders, 6–8px radii and almost no shadow, as Mews and other dense PMS tools do |

## 4. Direction for this pass (evidence-based)

1. **Use Mews' structure and colour language**, because receptionists who've used Mews or similar PMSs already know it:
   - A Timeline (rooms × days) with reservation bars.
   - Room status colours: Dirty orange, Clean blue, Inspected green, Out of service red, Out of order yellow.
   - Reservation colours: urgent orange, today blue, in-house dark grey, dashed = unconfirmed.
   - A right-side **detail window** with Check in, Check out, Confirm and Manage.
2. **Luxury palette, applied the way dense tools need it.** Luxury hotel identities lean on black, navy and gold. Data-dense UIs work best with mostly neutrals, one action colour, and colour reserved for status. So: neutral surfaces, **deep navy** as the single action colour, **champagne gold** only for brand marks, and status colours only for status.
3. **Separate the booking from the check-in**, add change room and cancel, and include **at least 6 refusal and failure cases** that you can trigger from the prototype dock.
4. **Truthful states everywhere:** a neutral data-source label, loading, empty (no rooms), 401, 403 `dev-origin-refused`, offline, conflict, and outcome unknown.
5. **Guest verification** through a short-lived invite code from the check-in SMS or the front desk, never phone digits or the QR alone.
6. **Staff, guest and live views are screens only.**

## 5. Results after this pass (verified in the running prototype, Nov 10)

| Area | Now | Status |
|---|---|---|
| Lead P0: provenance | Neutral **"Synthetic preview · not live data"** label. "Not connected" on 401/403. Sidebar counts are hidden whenever data isn't loaded. | Fixed |
| 8 KPIs | In house, Arrivals, Departures, Overdue, Ready, Not ready, Blocked, Open requests. Each one opens the matching filtered view. | Meets |
| Truthful states | Loading skeleton (counts hidden), No rooms yet, Signed out (401), **403 dev-origin-refused**, Offline (read-only, nothing queued). Every state is reachable from the dock. | Meets |
| Responsive | 1440 / 1366 / 1100: full rail. 768: icon rail, 4-column KPIs, horizontal table scroll. 390: bottom tab bar, full-width cards. | Meets (tested in an emulated pane; still needs a check on a real device) |
| WOR-38 | Walk-in **creates a booking** (with read-back) before a separate **check-in**. Check-in has a checklist: confirmed, room ready, lead ID checked, other adults' IDs checked. Also Move room (reason plus "guest is moving now"), Check-out (balance handoff, keys, Dirty plus cleaning task), Cancel (refused for checked-in stays). **Refusal cases:** invalid name, invalid phone, over capacity, no ready room of type, booking still pending, room not ready, ID not checked, conflict (room taken), save failed, outcome unknown with Check status, duplicate, 403 denied, offline. | Meets |
| WOR-39 | Reservations desk: status tabs; arrival, source, type and unassigned filters; RMY references; requested vs assigned room; rate and total; activity log; confirm against fresh availability with Recheck; **concurrency conflict** with a refreshed list; decline or cancel with a reason. | Meets |
| WOR-40 | Housekeeping and maintenance phones: list → detail → timeline → Accept, On my way, Done. **Can't do it** escalates with a reason. Maintenance can **block** a room and must confirm "safe to sell" to **release** it, which creates a cleaning task. A **supervisor** inspection queue handles Clean → Inspected. Offline banner. | Meets |
| WOR-41 | Public booking request: dates, guests, room types (photo placeholders), "looks available" wording (never "guaranteed"), form with consent, RMY reference, "not confirmed yet, no payment taken". | Meets |
| WOR-42 | QR landing shows **no guest data**. A **6-digit invite code** from the check-in SMS unlocks it, with wrong-code, locked and expired paths and a stay-ended state. My Stay home leads to category, request, review, a saved ticket reference and live tracking. Reopen is available after Done. | Meets |
| WOR-43 | Chat with **confirm before sending**. Saved ticket shown with live status. Voice: permission, then listening, then an **editable transcript**, with Say again or Type instead. Unclear requests go to the front desk, never a guess. Billing and safety go to a human, and privacy questions are refused. Human handoff pauses Roomay. **WhatsApp storyboard** marked "future integration, not live". | Meets |
| WOR-24 | First-run help strip on Today (dismissible, reopened from Help; the shortcut sentence hides on phones). "How your tasks work" card on staff phones. **Printable A4 quick start** (`#/docs/quickstart`). | Meets (usability test still open) |
| WOR-44 | Manager **Overview** (KPIs from records only, requests by team, repeat problems, blocked rooms with Release, needs-a-manager list), **Team and roles** with a 7-role permission matrix and Invite, **Hotel setup** checklist with a no-rooms state. | Meets (P2) |
| WOR-45 | Contrast AA held, focus rings, reduced motion, colour never used alone | Partial: **usability testing with two people is still blocked** |
| WOR-46 | **Copy deck**, **screen → route → data → permission → Pegment widget matrix**, token sheet and component sheet (`#/docs`, `#/kit`). The Figma master file is rebuilt from this app's screens by the designer's local sync tooling. | Meets once the plugin has been run in Figma |
| AI tells | All 12 tells in section 3 removed and re-checked on screen | Fixed |

**Figma re-sync (WOR-7, 36, 46):** the master file is rebuilt from **154 frames captured from this app** as editable layers. It also includes **34 component sets**, a "Roomay v3" variable collection, text and effect styles, and **44 click-through links**. Sections are organised by Linear issue. The capture tooling stays with the designer and is not part of `apps/web`.

**Still open (honest list):**
1. Run the Roomay v3 Sync plugin in the Figma desktop app and check the result (the MCP cap blocks reading the file from here).
2. Run the two-person usability test (WOR-45, WOR-24). The script is in the accessibility doc.
3. Check on real devices: an Android phone and a front-desk tablet.
4. Post Figma and prototype links to Linear for lead review (WOR-7, 35–46, 52), after the user approves.

## 6. Coverage against every assigned issue (re-checked against the Linear text, 11 Nov)

✅ = designed and in Figma. ⏳ = needs people or engineering, so it can't be finished by design alone.

| Issue | Design deliverables | Still open |
|---|---|---|
| **WOR-7** Lead | ✅ 3 Figma pages (Starter limit) with sections by issue. ✅ Journeys. ✅ Component library (34 sets). ✅ Exact copy and states. | ⏳ Post Figma links in Linear. ⏳ Review the compiled Workpeg UI with developers. ⏳ Lead approval. |
| **WOR-35** IA | ✅ Roles and navigation. ✅ Lifecycle. ✅ Decision points. ✅ Screen inventory with tables and issues. ✅ **One clickable end-to-end flow** (14 frames: walk-in → check-in → My Stay request → housekeeping resolves → check-out). | ⏳ Lead review. ⏳ Link screens to the implementation issues in Linear. |
| **WOR-36** Visual system | ✅ Tokens as variables and styles. ✅ Components with default, hover, focus, pressed, disabled, saving, error, stale, unauthorized, offline and empty states. ✅ Dates, overlays, tables, pagination, timelines and skeletons. ✅ 1440 / 1280 / 768 / 390 / 360. ✅ Pegment mapping and fallbacks. | ⏳ Developer review against the SDK. |
| **WOR-37** Today and rooms | ✅ Today with 8 KPIs. ✅ Timeline and Board. ✅ Detail panel. ✅ Legend. ✅ New walk-in and **New booking**. ✅ Check in / out, log request, report a problem. ✅ States: zero rooms, **no arrivals**, **all dirty**, overdue, loading, 401, 403, **400**, **timeout**, **partly loaded**, **out of date**, offline, unknown write. ✅ Tablet and phone. ✅ Phone numbers revealed only on request. | ⏳ The under-30-second "find a ready room / blocked room" test. |
| **WOR-38** Walk-in to checkout | ✅ Clickable flow. ✅ **Second adult named, with ID check per adult**. ✅ 9 refusal cases. ✅ Move with a reason. ✅ Checkout turns the room Dirty and sends a task. ✅ Cancel refused once checked in. | ⏳ Review with WOR-11 and WOR-12 developers. |
| **WOR-39** Reservations | ✅ Filters. ✅ Detail with audit. ✅ Confirm against live rooms. ✅ Conflict. ✅ Decline and cancel with a reason. ✅ **Change dates with a recheck, and a conflict**. ✅ **Unknown outcome** and **offline**. ✅ **New booking for a later date**. | ⏳ WOR-13 developer review. |
| **WOR-40** Department inbox | ✅ My tasks, detail and timeline. ✅ Accept → in progress → done. ✅ Can't do it. ✅ Block and safe-to-sell release. ✅ Supervisor inspection. ✅ Offline. ✅ **Race with another employee**, **send failed**, **not allowed**. ✅ **One ticket in three views**. ✅ Nav no longer promises "Team chat". | ⏳ Food and drink staff view is the same pattern as housekeeping, so it isn't drawn separately. |
| **WOR-41** Guest booking | ✅ Catalogue. ✅ Dates and guests. ✅ "Looks available" (provisional). ✅ Form, consent and errors. ✅ Pending reference with no payment. ✅ **Send failed**. ✅ **Group too big**. ✅ **Check a request later (reference + mobile + texted code)**. | ⏳ A desktop adaptation of the public page wasn't drawn; it is the mobile layout centred. |
| **WOR-42** My Stay | ✅ QR with nothing private. ✅ Invite code. ✅ Wrong, **locked** and expired codes. ✅ Home, request, review, ticket after save and tracking. ✅ **Done → reopen**. ✅ **Send failed**. ✅ Stay ended. | ⏳ Room-change and revoked-session states are covered by "stay ended" wording, not separate frames. |
| **WOR-43** Conversation | ✅ Confirm before sending. ✅ Saved ticket with live status. ✅ Unclear, billing, safety and privacy handling. ✅ Human handoff. ✅ Voice: permission, listening, editable transcript. ✅ WhatsApp storyboard marked future. ✅ State diagram and copy. | ⏳ The AI-timeout and provider-outage screens exist as copy and diagram only. |
| **WOR-44** Manager | ✅ Overview from records. ✅ Roles matrix. ✅ Invite. ✅ **Remove access with its effects**. ✅ Setup with a no-rooms state. ✅ **Release only after a repair check, with the incident history**. | ⏳ Lower priority. Engineering to confirm which permissions Workpeg enforces. |
| **WOR-45** Accessibility | ✅ Contrast computed from the tokens. ✅ Focus, order, targets and reduced motion. ✅ All widths. ✅ Every high-risk state. ✅ Honest terms. ✅ Test script. | ⏳ **Two-person task test (blocked: needs testers).** ⏳ Review of the compiled Workpeg UI. |
| **WOR-46** Handoff | ✅ Organised Figma, dated and owned. ✅ Token sheet. ✅ Screen → route → data → permission → widget matrix. ✅ Copy deck. ✅ Unsupported patterns with fallbacks. | ⏳ Walkthrough with the lead developer and sign-off. ⏳ Post links in Linear. |
| **WOR-24** Onboarding | ✅ Today first-run help. ✅ Staff "How your tasks work". ✅ Manager setup empty state. ✅ Help microcopy and error guidance. ✅ Printable quick start. | ⏳ Test with one unfamiliar teammate and log notes. |

---
### Sources
- Mews Help Center: [The Timeline — an overview](https://help.mews.com/s/article/The-Timeline-An-overview), [The Smart detail window](https://help.mews.com/s/article/The-Smart-detail-window-in-the-Timeline), [Managing reservations on the Timeline](https://help.mews.com/s/article/Managing-reservations-on-the-Timeline)
- Mews feedback on colour and accessibility: [Timeline visual appearance](https://feedback.mews.com/forums/918232-property-operations-pms/suggestions/47159095-impove-timeline-visual-appearance-for-improved-wor?page=2)
- AI-tell catalogs: [avoid-ai-design (GitHub)](https://github.com/funboy322/avoid-ai-design), [925studios — AI slop tells](https://www.925studios.co/blog/ai-slop-design-tells), [smoothui — AI design slop](https://smoothui.dev/blog/ai-design-slop), [designpixil — AI slop](https://designpixil.com/blog/ai-slop-design)
- Luxury hotel colour: [Skift — the colour choices of luxury hotel logos](https://skift.com/2019/05/21/the-story-behind-the-color-choices-of-luxury-hotel-logos), [Mandarin Oriental brand refresh](https://travelmarketreport.com/niche-luxury/articles/mandarin-oriental-refreshes-brand-identity-with-simplified-logo-and-new-color-palette)
- Semantic colour in dense UIs: [SAP Fiori — semantic colours](https://www.sap.com/design-system/fiori-design-web/v1-136/foundations/best-practices/ui-elements/how-to-use-semantic-colors), [ServiceTitan Anvil — semantic palette](https://anvil.servicetitan.com/docs/web/data-visualization/semantic-color-palette)
