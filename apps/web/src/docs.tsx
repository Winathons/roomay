import type { ReactNode } from "react";
import { IconArrowRight, IconCheck, IconX } from "@tabler/icons-react";

// Handoff documents (WOR-24, 35, 39, 43, 45, 46). Rendered in the product's own system, then captured into Figma.
const Doc = ({ title, issue, intro, children, w = 1200 }: { title: string; issue: string; intro: string; children: ReactNode; w?: number }) =>
  <div style={{ background: "var(--bg)", minHeight: "100vh", padding: 32 }}><article className="doc" style={{ width: w, margin: "0 auto", background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 8, padding: 40, display: "flex", flexDirection: "column", gap: 28 }}>
    <header style={{ display: "flex", gap: 16, alignItems: "flex-start", borderBottom: "1px solid var(--line)", paddingBottom: 20 }}><span className="mark" style={{ width: 34, height: 34, fontSize: 19 }}>R</span><div style={{ flex: 1 }}><div className="cap">{issue} · Roomay design handoff · v3 · 10 Nov 2026 · Owner: Design lead</div><h1 className="h-big" style={{ marginTop: 4, fontSize: 28, lineHeight: "34px" }}>{title}</h1><p className="ink2" style={{ marginTop: 6, maxWidth: 820 }}>{intro}</p></div></header>
    {children}</article></div>;
const Sec = ({ t, children, sub }: { t: string; sub?: string; children: ReactNode }) => <section style={{ display: "flex", flexDirection: "column", gap: 12 }}><div><h2 className="h-sec" style={{ fontSize: 18, lineHeight: "24px" }}>{t}</h2>{sub && <p className="muted" style={{ marginTop: 2 }}>{sub}</p>}</div>{children}</section>;
const T = ({ head, rows, wrap = true }: { head: string[]; rows: ReactNode[][]; wrap?: boolean }) => <div className="box"><table className="tbl"><thead><tr>{head.map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={wrap ? "wrap" : ""} style={{ verticalAlign: "top", paddingTop: 10, paddingBottom: 10 }}>{c}</td>)}</tr>)}</tbody></table></div>;
const C = ({ k, l }: { k: string; l: string }) => <span className={`chip s-${k}`}>{l}</span>;
const Yes = () => <IconCheck size={16} color="var(--insp)" stroke={2.6} />; const No = () => <IconX size={15} color="var(--oos)" stroke={2.4} />;

// ---------- WOR-35 product map ----------
function ProductMap() {
  const Step = ({ n, t, who, tbl, chip }: { n: string; t: string; who: string; tbl: string; chip: ReactNode }) => <div className="box" style={{ padding: 12, width: 196, display: "flex", flexDirection: "column", gap: 6 }}><span className="cap">Step {n}</span><b style={{ fontWeight: 600, lineHeight: "18px" }}>{t}</b>{chip}<span className="cap">{who}</span><span className="mono" style={{ fontSize: 11.5, color: "var(--clean)" }}>{tbl}</span></div>;
  const A = () => <IconArrowRight size={18} color="var(--text-4)" style={{ flex: "none", alignSelf: "center" }} />;
  return <Doc title="Product map: roles, navigation and the stay lifecycle" issue="WOR-35" intro="One hotel system on Workpeg. Every screen reads and writes the same Workpeg tables under staff permissions. Roomay suggests and routes; people approve anything about room safety, check-in, cancellations or money.">
    <Sec t="Roles and navigation" sub="Maximum five navigation items per role. Device priority follows how each role actually works.">
      <T head={["Role", "Device", "Navigation", "Main jobs", "Can't see"]} rows={[
        [<b>Receptionist</b>, "Desktop first, tablet", "Today · Rooms · Reservations · Requests · Guests", "Walk-ins, confirm requests, check in and out, move rooms, route requests", "Other hotels' data. Phone numbers stay hidden until revealed (logged)."],
        [<b>Housekeeping / Maintenance / F&B</b>, "Phone", "My tasks · Task detail · Updates · Me", "Accept, start, finish or escalate tasks. Maintenance blocks and releases rooms.", "Guest phone numbers, IDs, bills. First name and room only."],
        [<b>Supervisor</b>, "Phone", "Inspections · My tasks", "Pass or fail cleaned rooms (Clean → Inspected)", "Same as housekeeping"],
        [<b>Manager</b>, "Desktop", "Overview · Team and roles · Hotel setup", "Setup, roles, blocked rooms, escalations, repeat problems", "Nothing restricted, but views of personal data are logged"],
        [<b>Guest (verified)</b>, "Phone web", "My stay · Ask Roomay · Hotel", "Ask for services, track them, talk to a person", "Anything except their own stay"],
        [<b>Visitor (not verified)</b>, "Phone web", "Rooms · Booking request", "Browse rooms and send a booking request", "Any stay, guest or room status"],
      ]} />
    </Sec>
    <Sec t="End-to-end stay lifecycle" sub="Who acts at each step, what status changes, and which Workpeg table holds the record.">
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "stretch" }}>
        <Step n="1" t="Booking request" who="Guest, web or WhatsApp" tbl="reservations" chip={<span className="chip dash">Pending confirmation</span>} /><A />
        <Step n="2" t="Confirm against live rooms" who="Receptionist" tbl="reservations, rooms, room_blocks" chip={<C k="today" l="Confirmed" />} /><A />
        <Step n="3" t="Check in (ID, room Ready)" who="Receptionist" tbl="stays, stay_guests" chip={<C k="house" l="In house" />} /><A />
        <Step n="4" t="Guest asks for something" who="Guest → Roomay" tbl="service_requests" chip={<C k="neutral" l="Received" />} /><A />
        <Step n="5" t="Team handles it" who="Housekeeping / Maintenance" tbl="service_requests, audit" chip={<C k="insp" l="Resolved" />} />
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "stretch" }}>
        <Step n="1b" t="Walk-in: booking first" who="Receptionist" tbl="guests, reservations" chip={<C k="today" l="Confirmed" />} /><A />
        <Step n="5b" t="Unsafe room" who="Maintenance" tbl="room_blocks" chip={<C k="oos" l="Out of service" />} /><A />
        <Step n="6" t="Check out" who="Receptionist" tbl="stays" chip={<C k="dirty" l="Dirty" />} /><A />
        <Step n="7" t="Clean and inspect" who="Housekeeping, Supervisor" tbl="rooms" chip={<C k="insp" l="Inspected" />} /><A />
        <Step n="8" t="Room ready again" who="Derived, never stored" tbl="computed" chip={<span className="chip s-insp noswatch">Ready</span>} />
      </div>
    </Sec>
    <Sec t="Decision points every flow handles">
      <T head={["Situation", "What the design does"]} rows={[
        ["Room not ready at check-in", "Check-in is blocked with the reason. Ready rooms of the same type are offered. The booking moves with the guest."],
        ["Two receptionists book the same room", "The second save is refused with “Someone else changed this first”. Availability refreshes. Nothing is half-saved."],
        ["Guest past checkout", "Overdue on Today and in the Timeline. Staff choose: extend, or check out. Never automatic."],
        ["Guest not verified", "Room QR shows nothing private. A 6-digit invite code from the check-in SMS unlocks My Stay."],
        ["Request over its target time", "Over target on Today and Requests. Staff can send a reminder. The team can escalate with a reason."],
        ["Connection lost or save outcome unknown", "Read-only offline banner. Unknown outcomes ask staff to Check status before trying again, so nothing is done twice."],
        ["No rooms set up", "Front desk shows “No rooms set up yet”. Only a manager can add room types and rooms."],
      ]} />
    </Sec>
    <Sec t="Screen inventory and data sources">
      <T wrap={false} head={["Screen", "Role", "Priority", "Reads", "Writes", "Issue"]} rows={[
        ["Today", "Receptionist", "Desktop, tablet, phone", "rooms, stays, reservations, room_blocks, requests", "none on load", "WOR-37"],
        ["Rooms: Timeline and Board", "Receptionist", "Desktop, tablet", "rooms, room_types, stays, reservations, room_blocks", "rooms (cleaning status)", "WOR-37"],
        ["Walk-in, Check-in, Move, Check-out, Cancel", "Receptionist", "Desktop, tablet", "rooms, reservations, stays", "guests, reservations, stays, stay_guests, rooms", "WOR-38"],
        ["Reservations desk", "Receptionist", "Desktop", "reservations, rooms, room_blocks", "reservations", "WOR-39"],
        ["Requests", "Receptionist", "Desktop", "service_requests, audit", "service_requests", "WOR-37, 40"],
        ["My tasks, Task detail, Inspections", "Department staff", "Phone", "service_requests, rooms", "service_requests, rooms, room_blocks", "WOR-40"],
        ["Book a room", "Visitor", "Phone", "room_types (rates, capacity)", "reservations (pending)", "WOR-41"],
        ["Room QR, My Stay, Request, Track", "Guest", "Phone", "own stay, own requests", "service_requests", "WOR-42"],
        ["Ask Roomay, Voice, WhatsApp (future)", "Guest", "Phone", "own stay", "service_requests", "WOR-43"],
        ["Overview, Team and roles, Setup", "Manager", "Desktop", "all", "room_types, rooms, roles", "WOR-44"],
      ]} />
    </Sec>
  </Doc>;
}

// ---------- status glossary ----------
function Glossary() {
  return <Doc title="Status glossary" issue="WOR-36 · WOR-39 · WOR-45" intro="One word per state, everywhere. Occupancy, cleaning and maintenance are separate facts and are never merged into one colour. Every status shows text with its colour, never colour alone. Colours follow Mews, so receptionists who've used a modern PMS recognise them.">
    <Sec t="Room cleaning (set by housekeeping)"><T head={["Status", "Meaning", "Who changes it"]} rows={[[<C k="dirty" l="Dirty" />, "Needs cleaning. Set automatically at check-out and after a move.", "Housekeeping, receptionist"], [<C k="clean" l="Clean" />, "Cleaned, waiting for a supervisor check.", "Housekeeping"], [<C k="insp" l="Inspected" />, "Cleaned and checked. Can be given to a guest.", "Supervisor, manager only"]]} /></Sec>
    <Sec t="Room blocks (set by maintenance or a manager)"><T head={["Status", "Meaning", "Release"]} rows={[[<C k="oos" l="Out of service" />, "Urgent problem. No guest can be checked in. Usually hours.", "Maintenance or manager, after checking the repair"], [<C k="ooo" l="Out of order" />, "Long-term work. Not for sale for days.", "Manager"]]} /></Sec>
    <Sec t="Occupancy (from stays, never from bookings)"><T head={["Status", "Meaning"]} rows={[[<C k="neutral" l="Vacant" />, "No active stay."], [<C k="today" l="Arrives today" />, "A confirmed booking arrives today. The room isn't occupied yet."], [<C k="house" l="In house" />, "A checked-in stay with a later departure."], [<C k="today" l="Departs today" />, "Due out at 11:00 today."], [<C k="urgent" l="Overdue" />, "Past check-out time and still in the room."], [<span className="chip s-insp noswatch">Ready</span>, "Derived: vacant, cleaned, not blocked. Never stored."]]} /></Sec>
    <Sec t="Bookings (request ≠ booking ≠ stay)"><T head={["Status", "Meaning"]} rows={[[<span className="chip dash">Pending confirmation</span>, "A request. No room is held. Staff must confirm against live rooms."], [<C k="today" l="Confirmed" />, "A room is held for these dates."], [<C k="house" l="Checked in" />, "A stay exists. It can't be cancelled, only checked out."], [<C k="neutral" l="Checked out" />, "Finished. Kept for records."], [<C k="oos" l="Cancelled" />, "Cancelled or declined, with a reason in the history."]]} /></Sec>
    <Sec t="Requests"><T head={["Status", "Meaning"]} rows={[[<C k="neutral" l="Received" />, "Saved. If the team is unclear, it waits for the front desk to route it."], [<C k="today" l="Assigned" />, "Sent to a team and person."], [<C k="today" l="Acknowledged" />, "The person has seen it."], [<C k="navy" l="In progress" />, "Someone is on the way or working on it."], [<C k="insp" l="Resolved" />, "Done. The guest sees it at once and can reopen it."], [<C k="urgent" l="Escalated" />, "The team couldn't do it. The front desk decides."], [<C k="neutral" l="Cancelled" />, "Not needed, or closed at check-out."], [<C k="urgent" l="Over target" />, "Open longer than the team's target time."]]} /></Sec>
  </Doc>;
}

// ---------- WOR-46 copy deck ----------
function Copy() {
  return <Doc title="Copy deck and content style" issue="WOR-46" intro="Plain, warm English for Nigerian hotels. Short words, sentence case, no jargon. Easy to translate: no idioms, no text inside images. Never promise what the system hasn't done.">
    <Sec t="Voice rules"><T head={["Do", "Don't"]} rows={[["“Check in to 205”", "“Proceed with check-in operation”"], ["“Couldn't save. Nothing was changed.”", "“Error 500” or “Something went wrong”"], ["“Pending confirmation. No room is held yet.”", "“Booked!” before staff confirm"], ["“Recorded by staff. Roomay doesn't take payments.”", "Any card, payment or receipt wording"], ["Last name, first name in staff lists (Okafor, Ada)", "Nicknames or guest phone numbers in lists"]]} /></Sec>
    <Sec t="What happens when a save doesn't go through" sub="Exact copy for every write in the product. One component, the same wording everywhere."><T head={["Outcome", "Title", "Body", "Action"]} rows={[
      ["Conflict", "Someone else changed this first.", "{What happened}. Nothing of yours was saved. The list below is refreshed.", "Pick again"],
      ["Failed", "Couldn't save.", "Nothing was changed. Check the connection and try again.", "Try again"],
      ["Outcome unknown", "We couldn't confirm this saved.", "The connection dropped before Workpeg replied. Don't submit again. Check first, so the guest isn't {checked in} twice.", "Check status"],
      ["Duplicate", "Already saved.", "This was submitted twice. Roomay kept one record: {RMY-1043}. Nothing else changed.", "None"],
      ["Denied (403)", "Your role can't do this.", "Workpeg refused the change (403). Ask a manager to do it or to update your role.", "None"],
      ["Offline", "You're offline.", "Nothing was sent. Reconnect, then try again.", "Retry"],
    ]} /></Sec>
    <Sec t="Key actions and confirmations"><T head={["Place", "Copy"]} rows={[
      ["Walk-in button", "New walk-in"], ["Walk-in subtitle", "Creates a booking. Check-in is the next step."], ["Booking saved", "{RMY-1043} is saved and confirmed. {205} is held for {Chioma}. The guest is not checked in yet."],
      ["Check-in list", "Booking is confirmed · Room {205} is ready · {Ada}'s ID checked · IDs checked for the other adults"], ["ID note", "Roomay records that the ID was checked, not the number or a photo."],
      ["Check-out note", "Checking out sets {204} to Dirty, sends a cleaning task to housekeeping, and closes open requests."], ["Move confirmation", "The guest knows and is moving now. Room {204} is only freed once they've moved."],
      ["Cancel refused", "{Ada} is already checked in. A stay can't be cancelled. Use Check out or Move room."], ["Inspected disabled", "Only a housekeeping supervisor can mark a room Inspected."], ["Release block", "Is room {305} safe to sell? Check the repair yourself."],
    ]} /></Sec>
    <Sec t="Empty and system states"><T head={["State", "Title", "Body"]} rows={[
      ["Loading", "(skeleton)", "Loading rooms and stays from Workpeg… Counts stay hidden until they arrive."], ["No rooms", "No rooms set up yet", "Roomay needs your room types and rooms before you can take walk-ins or bookings. A manager sets this up once."],
      ["401", "You've been signed out", "Your Workpeg session ended. Sign in again to continue."], ["403", "Roomay can't reach this hotel's records", "Workpeg refused the request (403 · dev-origin-refused). No hotel data is shown. Nothing was changed."],
      ["Offline", "You're offline.", "You can still look things up. Changes are paused until the connection is back. Nothing is queued."], ["No filter match", "No rooms match", "Nothing fits these filters. Clear them to see every room."],
      ["Requests empty", "No requests here", "New guest requests appear here the moment they're sent."], ["Staff empty", "(none)", "Nothing waiting. New tasks appear here straight away."],
    ]} /></Sec>
    <Sec t="Guest messages"><T head={["Place", "Copy"]} rows={[
      ["QR landing", "Welcome to room {204}. To see your stay or ask for anything, enter the 6-digit code from your check-in text message."], ["Wrong code", "That code doesn't match. {2} tries left before it locks for 10 minutes."], ["Expired", "This code has expired. Codes last 24 hours. Ask the front desk for a new one."],
      ["Booking request sent", "Your reference is {RMY-1061}. This is a booking request, not a confirmed booking yet. No payment has been taken."], ["Chat confirm", "I'll send this to {Housekeeping} for room {204}. It usually takes about {15} minutes."],
      ["Unclear", "I'm not sure which team handles that, so I've passed it to the front desk instead of guessing."], ["Handoff", "Amaka at the front desk will reply here. I'll stay quiet until she's done."], ["Billing", "Billing questions are handled by a person. I won't change any charges."], ["Privacy", "Sorry, I can't share anything about other rooms or guests."], ["Safety", "If anyone is in danger, call the front desk now on 0, or leave the room. I've alerted the duty manager."],
    ]} /></Sec>
  </Doc>;
}

// ---------- WOR-46 screen matrix ----------
function Matrix() {
  return <Doc title="Screen → route → data → permission" issue="WOR-46" intro="What developers need to build each screen in the Workpeg Python UI without guessing. Every write shows a pending state, then reads back the saved record before showing success.">
    <T wrap head={["Screen", "Route (suggested)", "Data", "Who", "Writes and read-back", "Pegment widgets"]} rows={[
      ["Today", "/b/[id]/reception", "rooms, stays, reservations, room_blocks, service_requests", "Receptionist, Manager", "None on load. Row actions open sheets.", "Container card, Table, Tabs, Tag, Button"],
      ["Rooms timeline", "/b/[id]/reception/rooms", "rooms, room_types, stays, reservations, room_blocks", "Receptionist, Manager", "Cleaning status: write, then re-read room", "GridView/Row for the grid; Container for bars (absolute)"],
      ["Rooms board", "same, view=board", "same", "Receptionist", "same", "GridView(columns), Container card"],
      ["Detail panel", "panel state in route", "one room / reservation / request + audit", "Receptionist", "Confirm, extend, release: write, read back, update audit list", "Row + Container side panel (no Drawer in Pegment)"],
      ["Walk-in", "sheet", "room_types, rooms, reservations", "Receptionist", "Create reservation, read back RMY ref, then offer check-in", "Modal or side panel, Input, Stepper (Row + Buttons), RadioGroup"],
      ["Check-in", "sheet", "reservation, rooms, stays", "Receptionist", "Create stay and stay_guests, read back, toast with Undo", "Checkbox, Select, Button"],
      ["Check-out", "sheet", "stay, service_requests", "Receptionist", "End stay, set room Dirty, create cleaning task, close requests", "Checkbox, Button"],
      ["Move room", "sheet", "stay, rooms", "Receptionist", "Update stay room, old room Dirty, audit reason", "Select, Checkbox"],
      ["Reservations", "/b/[id]/reception/reservations", "reservations", "Receptionist", "Confirm with fresh availability; cancel with reason", "Tabs, Table(search, page_size), Select"],
      ["Requests", "/b/[id]/reception/requests", "service_requests, audit", "Receptionist", "Route, resolve, cancel", "Tabs, Table, Select"],
      ["My tasks", "/b/[id]/staff", "service_requests (own team), rooms", "Dept staff", "Acknowledge, start, resolve, escalate", "ListView, Button(full_width)"],
      ["Inspections", "/b/[id]/staff/inspect", "rooms", "Supervisor", "Clean → Inspected or Dirty", "ListView, Button"],
      ["Book a room", "public /book", "room_types", "Visitor", "Create pending reservation, read back RMY ref", "Input, DateInput, Checkbox"],
      ["My Stay", "public /stay/[room]", "own stay only (after invite code)", "Verified guest", "Create request, show ticket ref after save", "TextInput, ListView, Wizard"],
      ["Ask Roomay", "public /stay/[room]/chat", "own stay", "Verified guest", "Create request only after the guest confirms", "ChatInput, Markdown, Button"],
      ["Manager", "/b/[id]/manage", "all", "Manager", "Setup tables, roles, release blocks", "Table, Tabs, Modal"],
    ]} />
    <Sec t="Not supported natively, with the fallback"><T head={["Pattern", "Fallback in Workpeg"]} rows={[["Side drawer", "Row with a fixed-width Container panel, or Modal on phones"], ["Timeline bars", "Absolute Containers inside a Stack per row, or a Table with coloured cells as the minimum"], ["Keyboard shortcuts (N, /)", "Nice to have. Only if Pegment exposes key events; buttons always exist."], ["Hover states", "Through style= :hover blocks. Never needed for meaning."], ["Live updates", "StreamBuilder / table-change listeners; otherwise refresh on focus with “Updated hh:mm”."]]} /></Sec>
  </Doc>;
}

// ---------- WOR-45 accessibility ----------
const hex = (h: string) => { h = h.replace("#", ""); return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16) / 255).map(c => c <= .03928 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4); };
const lum = (h: string) => { const [r, g, b] = hex(h); return .2126 * r + .7152 * g + .0722 * b; };
const ratio = (a: string, b: string) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
function A11y() {
  const pairs: [string, string, string, string][] = [["Body text", "#101828", "#FFFFFF", "text on surface"], ["Secondary text", "#5D6676", "#FFFFFF", "text-3 on surface"], ["Secondary on page bg", "#5D6676", "#F3F4F6", "text-3 on bg"], ["Primary button", "#FFFFFF", "#1D3557", "white on navy"], ["Link / navy text", "#1D3557", "#FFFFFF", "navy on surface"], ["Dirty chip", "#B54708", "#FEF3E6", "dirty"], ["Clean chip", "#175CD3", "#EBF3FF", "clean"], ["Inspected chip", "#067647", "#E8F6EE", "inspected"], ["Out of service chip", "#B42318", "#FDEDEB", "oos"], ["Out of order chip", "#8A5A00", "#FEF6DA", "ooo"], ["In house chip", "#344054", "#ECEEF2", "house"], ["Overdue chip", "#C4320A", "#FFF1EA", "urgent"], ["Sidebar text", "#C7CCD4", "#111827", "on ink"], ["Gold brand text", "#8A6A35", "#FFFFFF", "gold-ink"], ["Disabled text", "#98A2B3", "#F8F9FA", "exempt (disabled)"]];
  return <Doc title="Accessibility, responsive and truthful-state audit" issue="WOR-45" intro="Checked against the coded prototype that this Figma is captured from. Contrast is calculated from the real token values, not estimated. Real-device checks and the two-person task test are listed as open.">
    <Sec t="Contrast (WCAG 2.2: text needs 4.5:1, large text and UI parts 3:1)"><T wrap={false} head={["Pair", "Foreground", "Background", "Ratio", "AA"]} rows={pairs.map(([n, f, b, note]) => { const r = ratio(f, b); return [<b style={{ fontWeight: 500 }}>{n}</b>, <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}><i style={{ width: 14, height: 14, borderRadius: 3, background: f, border: "1px solid var(--line)" }} /><span className="mono">{f}</span></span>, <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}><i style={{ width: 14, height: 14, borderRadius: 3, background: b, border: "1px solid var(--line)" }} /><span className="mono">{b}</span></span>, <b className="num">{r.toFixed(1)}:1</b>, note.startsWith("exempt") ? <span className="cap">Exempt</span> : r >= 4.5 ? <Yes /> : <No />]; })} /></Sec>
    <Sec t="Checks"><T head={["Check", "Result", "Notes"]} rows={[
      ["Colour is never the only signal", <Yes />, "Every status chip has text. Timeline bars carry names; blocks have hatching and words."],
      ["Visible keyboard focus", <Yes />, "2px navy outline with 2px offset on every interactive element."],
      ["Logical tab order", <Yes />, "Sidebar → top bar → page actions → KPIs → table → side panel. Sheets trap focus; Esc closes."],
      ["Touch targets on phones", <Yes />, "Staff and guest actions are 48px tall. List rows are at least 60px."],
      ["Reduced motion", <Yes />, "Animations collapse to 1ms under prefers-reduced-motion. Only panels and sheets animate."],
      ["Form errors", <Yes />, "Text under the field with an icon, red outline, and the field keeps its label."],
      ["Screen-reader labels", <Yes />, "Icon buttons have aria-labels; status updates use aria-live toasts."],
      ["Widths 1440 / 1366 / 1280 / 768 / 390 / 360", <Yes />, "No horizontal page scroll at any of them (checked in an emulated viewport). Tables scroll inside their card on tablet."],
      ["Real devices (Android phone, front-desk tablet)", <span className="cap">Open</span>, "Prototype checked in an emulated viewport only."],
      ["Two-person task test", <span className="cap">Blocked</span>, "Needs two people who haven't seen Roomay. Script below."],
    ]} /></Sec>
    <Sec t="Truthful states covered"><T head={["State", "Where", "Design"]} rows={[["Loading", "Front desk", "Skeleton; counts hidden so nothing shows 0 by mistake"], ["400 unknown hotel", "Front desk", "Wrong business selected; nothing shown"], ["Timeout", "Front desk", "Slow backend; try again, no counts"], ["Partly loaded", "Front desk", "Banner names what didn't load"], ["Out of date", "Front desk", "Last updated time and a Refresh"], ["No rooms configured", "Front desk, Setup", "Empty state, manager-only action"], ["401 signed out", "Front desk", "Sign-in prompt, returns to the same page"], ["403 dev-origin-refused", "Front desk", "Actual live error copy, no data, neutral “Not connected” label"], ["Offline", "All", "Read-only banner, writes disabled, nothing queued"], ["Stale availability", "Reservations", "“Checked at hh:mm”, Recheck, conflict refusal"], ["Saved / not saved / unknown / duplicate / denied", "Every write", "One WriteAlert component with exact copy"], ["AI unsure", "Chat, Requests", "Sent to the front desk instead of guessing"]]} /></Sec>
    <Sec t="Task test script (run with two people new to Roomay)"><T head={["Task", "Success looks like", "Watch for"]} rows={[["A guest walks in for one night. Book and check them in.", "Booking saved, then check-in with ID ticked, in under 2 minutes", "Do they understand booking and check-in are separate?"], ["Which room should Tolu Bello go to at 14:00?", "Spots that 210 is Dirty and uses the suggested room", "Do they notice the Dirty chip?"], ["Find a room that's blocked and say why", "Finds 305 Out of service, AC leaking, within 30 seconds", "Do they confuse Dirty and Out of service?"], ["As housekeeping, finish the towels request", "Accept → On my way → Done", "Do they find “Can't do it”?"], ["As a guest, ask for drinking water", "Enters code, confirms, sees tracker", "Do they trust the confirmation step?"]]} /></Sec>
  </Doc>;
}

// ---------- WOR-43 conversation states ----------
function Conversation() {
  const N = ({ t, k = "neutral", s }: { t: string; k?: string; s?: string }) => <div className="box" style={{ padding: "10px 12px", minWidth: 170 }}><span className={`chip s-${k}`}>{t}</span>{s && <div className="cap" style={{ marginTop: 6 }}>{s}</div>}</div>;
  const A = ({ l }: { l?: string }) => <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "var(--text-3)", fontSize: 12 }}>{l}<IconArrowRight size={16} /></span>;
  const R = ({ children }: { children: ReactNode }) => <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>{children}</div>;
  return <Doc title="Ask Roomay: conversation states and channel rules" issue="WOR-43" intro="Roomay is not a general chatbot. Every conversation either becomes a real Workpeg request the guest has confirmed, or goes to a person. Roomay never checks guests out, releases rooms, changes bookings or touches money.">
    <Sec t="Typed request">
      <R><N t="Verified guest" k="insp" s="Invite code accepted" /><A /><N t="Guest message" /><A /><N t="Understanding" s="Typing indicator" /><A l="clear" /><N t="Confirm card" k="today" s="Team, item, room, usual time" /><A l="Send" /><N t="Saved" k="insp" s="Shows TCK ref only after save" /><A /><N t="Live status" k="navy" s="Assigned → Done" /></R>
      <R><N t="Understanding" /><A l="unclear" /><N t="Sent to front desk" s="“Instead of guessing”" /><A /><N t="Staff reply in chat" /></R>
      <R><N t="Understanding" /><A l="billing / refund" /><N t="Human handoff" k="urgent" s="Roomay won't change charges" /></R>
      <R><N t="Understanding" /><A l="safety words" /><N t="Safety reply" k="oos" s="Call 0 now, duty manager alerted" /></R>
      <R><N t="Understanding" /><A l="other room / guest" /><N t="Refuse politely" s="Never shares other guests' details" /></R>
      <R><N t="Any time" /><A l="Talk to a person" /><N t="Human handoff" k="urgent" s="Roomay paused until staff finish" /></R>
      <R><N t="Understanding" /><A l="timeout or AI down" /><N t="Fallback" s="“I can't read that right now. Sent to the front desk.”" /></R>
    </Sec>
    <Sec t="Voice intake (browser speech)"><R><N t="Mic tapped" /><A /><N t="Permission" s="Allow, or Type instead" /><A l="Allow" /><N t="Listening" k="oos" s="Live partial transcript" /><A l="Stop" /><N t="Edit transcript" s="Send, Say again, Type instead" /><A /><N t="Typed flow" /></R>
      <T head={["Failure", "What the guest sees"]} rows={[["Mic blocked", "“Microphone is off for this site. Type your request instead.”"], ["Speech not supported", "Mic button hidden. Text only."], ["Noisy or empty transcript", "“I didn't catch that. Try again or type it.”"], ["Low bandwidth", "Voice disabled with a note; text still works."]]} /></Sec>
    <Sec t="WhatsApp (future integration, not live)"><T head={["Rule", "Design"]} rows={[["Opt-in", "First message states the hotel name and STOP to opt out"], ["Bookings", "Always a pending request with an RMY reference"], ["In-stay requests", "Ask for the invite code before showing anything about a stay"], ["24-hour window", "After 24 hours only approved templates can be sent (Meta rule)"], ["Human handoff", "Roomay pauses while staff reply"], ["Approval", "Needs a Meta Business account and approved templates before it's real"]]} /></Sec>
  </Doc>;
}

// ---------- WOR-24 quick start (printable A4) ----------
function QuickStart() {
  return <Doc w={794} title="Roomay quick start" issue="WOR-24" intro="A 3-minute read for new front desk and department staff. Print it and keep it at the desk.">
    <Sec t="The three things every room shows"><T head={["Thing", "Words you'll see"]} rows={[["Who's in it", "Vacant · Arrives today · In house · Departs today · Overdue"], ["Is it clean", <span><C k="dirty" l="Dirty" /> <C k="clean" l="Clean" /> <C k="insp" l="Inspected" /></span>], ["Is it blocked", <span><C k="oos" l="Out of service" /> <C k="ooo" l="Out of order" /></span>]]} /><p>A room is <b>Ready</b> only when it's empty, cleaned and not blocked.</p></Sec>
    <Sec t="Front desk: your first walk-in"><ol style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 6 }}><li>Press <b>New walk-in</b> (or N). Enter the name as on their ID, and their mobile.</li><li>Pick a room type and nights. Roomay only offers ready rooms, best first.</li><li>Record what they've paid, then <b>Create booking</b>. This holds the room.</li><li>Check their ID, tick the boxes, then <b>Check in</b>. They get a My Stay text.</li></ol></Sec>
    <Sec t="Front desk: check-out"><p>Open the stay, confirm the bill is settled and keys are back, then <b>Check out</b>. The room turns Dirty and housekeeping gets a task by itself.</p></Sec>
    <Sec t="Housekeeping and maintenance"><ol style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 6 }}><li>Open <b>My tasks</b>. Urgent ones are at the top.</li><li><b>Accept</b>, then <b>On my way</b> or <b>Start cleaning</b>, then <b>Done</b>.</li><li>Can't do it? Tap <b>Can't do it</b> and pick why. The front desk takes over.</li><li>Room unsafe? Maintenance taps <b>Block room</b>. Only release it after checking the repair.</li></ol></Sec>
    <Sec t="If something goes wrong"><T head={["You see", "Do this"]} rows={[["Couldn't save", "Nothing changed. Try again."], ["We couldn't confirm this saved", "Don't repeat it. Tap Check status first."], ["Someone else changed this first", "Pick another room from the refreshed list."], ["You're offline", "Look things up only. Wait for the connection."], ["Your role can't do this", "Ask your manager."]]} /></Sec>
    <p className="cap">Help: Getting started in the menu. Questions: your duty manager.</p>
  </Doc>;
}

// ---------- WOR-36/46 tokens ----------
function Tokens() {
  const css = getComputedStyle(document.documentElement);
  const v = (n: string) => css.getPropertyValue(n).trim();
  const groups: [string, string[]][] = [["Neutrals", ["--bg", "--surface", "--sunken", "--hover", "--selected", "--line", "--line-2", "--text", "--text-2", "--text-3", "--text-4"]], ["Brand", ["--ink", "--navy", "--navy-hover", "--navy-soft", "--gold", "--gold-ink"]], ["Status text", ["--dirty", "--clean", "--insp", "--oos", "--ooo", "--house", "--urgent"]], ["Status background", ["--dirty-bg", "--clean-bg", "--insp-bg", "--oos-bg", "--ooo-bg", "--house-bg", "--urgent-bg"]], ["Status swatch", ["--dirty-sw", "--clean-sw", "--insp-sw", "--oos-sw", "--ooo-sw", "--house-sw", "--urgent-sw"]]];
  return <Doc title="Design tokens" issue="WOR-36 · WOR-46" intro="The values every screen uses. Variable names match the CSS custom properties in the prototype. Pegment Theme keys: page = --bg, surface = --surface, bg = --surface, sidebar = --ink, fg = --text, muted = --text-3, border = --line, primary = --navy, primary_fg = #FFFFFF, radius = 6px, font = IBM Plex Sans.">
    {groups.map(([g, ks]) => <Sec key={g} t={g}><div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 12 }}>{ks.map(k => <div key={k} style={{ display: "flex", flexDirection: "column", gap: 4 }}><div style={{ height: 48, borderRadius: 6, background: `var(${k})`, border: "1px solid var(--line)" }} /><b style={{ fontWeight: 500, fontSize: 13 }}>{k.replace("--", "")}</b><span className="mono" style={{ fontSize: 11.5 }}>{v(k)}</span></div>)}</div></Sec>)}
    <Sec t="Type"><T head={["Style", "Font", "Size / line", "Use"]} rows={[[<span className="h-big">Page title</span>, "Century Gothic Bold (fallback Questrial)", "26 / 32", "Page headings"], [<span className="h-page">Panel title</span>, "Century Gothic Bold", "22 / 28", "Panels, sheets, top bar 18"], [<span className="h-sec">Section</span>, "Century Gothic Bold", "15 / 20", "Card and section titles"], ["Body", "IBM Plex Sans Regular", "14 / 20", "Everything else"], [<span className="lbl">Label</span>, "IBM Plex Sans Medium", "13 / 18", "Buttons, form labels"], [<span className="cap">Caption</span>, "IBM Plex Sans Regular", "12 / 16", "Meta text, never below 12"], [<span className="mono">RMY-1043</span>, "IBM Plex Mono", "12.5", "References and codes"]]} /></Sec>
    <Sec t="Spacing, size and radius"><T head={["Token", "Value", "Use"]} rows={[["Spacing", "4 · 8 · 12 · 16 · 20 · 24 · 32", "4 icon gap · 8 inline · 12 dense · 16 card padding · 24 page padding"], ["Control height", "36 · 30 · 48", "Default · compact in tables · touch (phones)"], ["Radius", "4 · 6 · 8 · 12", "Chips · controls · cards and panels · popovers"], ["Breakpoints", "1366 · 1180 · 860 · 600", "Full sidebar · icon rail · tablet · phone with bottom tabs"], ["Motion", "120–280 ms ease-out", "Panels and sheets only. Removed with reduced motion."]]} /></Sec>
  </Doc>;
}

export const DOCS = [
  { id: "productmap", title: "Product map: roles, navigation and lifecycle", issue: "WOR-35" },
  { id: "glossary", title: "Status glossary", issue: "WOR-36, 39, 45" },
  { id: "tokens", title: "Design tokens", issue: "WOR-36, 46" },
  { id: "conversation", title: "Ask Roomay conversation states", issue: "WOR-43" },
  { id: "a11y", title: "Accessibility and truthful-state audit", issue: "WOR-45" },
  { id: "copy", title: "Copy deck", issue: "WOR-46" },
  { id: "matrix", title: "Screen → route → data → permission", issue: "WOR-46" },
  { id: "quickstart", title: "Printable quick start", issue: "WOR-24" },
];
export function Docs({ id }: { id: string }) {
  const map: Record<string, () => ReactNode> = { productmap: ProductMap, glossary: Glossary, copy: Copy, matrix: Matrix, a11y: A11y, conversation: Conversation, quickstart: QuickStart, tokens: Tokens };
  const D = map[id] || ProductMap; return <D />;
}
