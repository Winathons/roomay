import { useEffect, useRef, useState, type ReactNode } from "react";
import { IconAlertTriangle, IconBell, IconCheck, IconChevronLeft, IconChevronRight, IconCircleCheck, IconHome, IconInfoCircle, IconListCheck, IconLock, IconMessageCircle, IconMicrophone, IconPhone, IconSend, IconUser, IconWifi, IconWifiOff } from "@tabler/icons-react";
import { useStore, type WriteResult } from "./store";
import { now, hhmm, when, day, naira, typeOf, ROOM_TYPES, STAFF, HOTEL, isOpen, triage, eligibleRooms, type Request, type Dept, roomView } from "./data";
import { ReqChip, Sla, SaveBtn, WriteAlert, Opt, Stepper } from "./ui";

export function Phone({ children, label }: { children: ReactNode; label: string }) {
  const [t, setT] = useState(hhmm(now()));
  useEffect(() => { const i = setInterval(() => setT(hhmm(now())), 10_000); return () => clearInterval(i); }, []);
  return <div className="phone" role="region" aria-label={label}><div className="screen"><div className="island" /><div className="statusbar"><span className="num">{t}</span><span className="sys"><IconWifi size={16} stroke={2.2} /><svg width="25" height="12" viewBox="0 0 25 12" aria-hidden><rect x=".5" y=".5" width="21" height="11" rx="3" fill="none" stroke="currentColor" opacity=".5" /><rect x="2" y="2" width="15" height="8" rx="1.5" fill="currentColor" /><rect x="22.5" y="4" width="2" height="4" rx="1" fill="currentColor" opacity=".5" /></svg></span></div>{children}<div className="home-ind" /></div></div>;
}
function Top({ title, sub, back, right }: { title: string; sub?: string; back?: () => void; right?: ReactNode }) {
  return <div className="m-top">{back && <button className="icon-btn" onClick={back} aria-label="Back" style={{ marginLeft: -8 }}><IconChevronLeft /></button>}<div style={{ flex: 1, minWidth: 0 }}><div className="m-title ellipsis">{title}</div>{sub && <div className="cap">{sub}</div>}</div>{right}</div>;
}
function Offline() { const { data } = useStore(); return data === "offline" ? <div className="alert neutral" style={{ borderRadius: 0, borderWidth: "0 0 1px", fontSize: 13 }}><IconWifiOff /><div>Offline. You can read tasks, but updates wait until you're back online.</div></div> : null; }

// =====================================================================
// Staff: Housekeeping / Maintenance / Supervisor (WOR-40)
// =====================================================================
type Role = "housekeeping" | "maintenance" | "supervisor";
export function StaffApp({ role }: { role: Role }) {
  const { db } = useStore();
  const [open, setOpen] = useState<string | null>(null);
  const [tab, setTab] = useState<"todo" | "done">("todo");
  const [intro, setIntro] = useState(true);
  const me = role === "housekeeping" ? STAFF.housekeeping : role === "maintenance" ? STAFF.maintenance : STAFF.supervisor;
  const dept: Dept = role === "maintenance" ? "Maintenance" : "Housekeeping";
  if (role === "supervisor") return <Supervisor />;
  const mine = db.requests.filter(q => q.dept === dept && q.status !== "cancelled");
  const todo = mine.filter(q => isOpen(q)).sort((a, b) => (b.priority === "urgent" ? 1 : 0) - (a.priority === "urgent" ? 1 : 0) || a.createdAt - b.createdAt);
  const done = mine.filter(q => q.status === "resolved");
  const q = open ? db.requests.find(x => x.id === open) : undefined;
  if (q) return <TaskDetail q={q} me={me} role={role} back={() => setOpen(null)} />;
  const list = tab === "todo" ? todo : done;
  return <>
    <Top title="My tasks" sub={`${me} · ${dept}`} right={<span className="avatar">{me.split(" ").map(x => x[0]).join("")}</span>} />
    <Offline />
    <div style={{ padding: "10px 16px", background: "var(--surface)", borderBottom: "1px solid var(--line)" }}>
      <div className="seg" style={{ width: "100%", display: "grid", gridTemplateColumns: "1fr 1fr" }} role="radiogroup" aria-label="Tasks">
        <button className={tab === "todo" ? "on" : ""} onClick={() => setTab("todo")} style={{ justifyContent: "center", height: 34 }}>To do <span className="n">{todo.length}</span></button>
        <button className={tab === "done" ? "on" : ""} onClick={() => setTab("done")} style={{ justifyContent: "center", height: 34 }}>Done <span className="n">{done.length}</span></button>
      </div>
    </div>
    <div className="m-scroll">
      {intro && tab === "todo" && <div className="m-card" style={{ marginTop: 12, padding: 16, display: "flex", flexDirection: "column", gap: 10 }} aria-label="How tasks work">
        <b style={{ fontFamily: "var(--head)", fontSize: 16 }}>How your tasks work</b>
        <ol style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 4, fontSize: 14 }}><li><b>Accept</b> so the front desk knows you've seen it.</li><li>Tap <b>{role === "housekeeping" ? "Start cleaning" : "I'm on my way"}</b> when you start.</li><li>Tap <b>{role === "housekeeping" ? "Cleaning done" : "Mark done"}</b> when it's finished. The guest sees it straight away.</li></ol>
        <div className="cap">Stuck? Tap <b>Can't do it</b> and the front desk takes over. You only see your team's tasks, and guests' phone numbers stay private.</div>
        <button className="btn secondary touch" onClick={() => setIntro(false)}>Got it</button></div>}
      {list.length === 0 && <div style={{ padding: "48px 24px", textAlign: "center" }} className="muted">{tab === "todo" ? "Nothing waiting. New tasks appear here straight away." : "Finished tasks show here."}</div>}
      {list.length > 0 && <div className="m-card" style={{ marginTop: 12 }}>{list.map(t => { const arr = db.reservations.find(r => r.roomId === t.roomId && r.status === "confirmed" && r.arrivalDay === 0); return (
        <button key={t.id} className="m-row" onClick={() => setOpen(t.id)}>
          <span style={{ fontFamily: "var(--head)", fontWeight: 700, fontSize: 22, width: 52, fontVariantNumeric: "tabular-nums" }}>{t.roomId}</span>
          <span style={{ flex: 1, minWidth: 0 }}><span style={{ display: "flex", gap: 6, alignItems: "center" }}><b style={{ fontWeight: 600, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{t.title}</b>{t.priority === "urgent" && isOpen(t) && <span className="chip s-urgent">Urgent</span>}</span>
            <span style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4, flexWrap: "wrap" }}><ReqChip s={t.status} /><Sla q={t} compact /></span>
            {arr && t.kind === "turnover" && isOpen(t) && <span className="cap" style={{ display: "block", marginTop: 4, color: "var(--today)" }}>Guest arriving {arr.eta}</span>}</span>
          <IconChevronRight size={18} color="var(--text-4)" />
        </button>); })}</div>}
    </div>
    <nav className="m-tabs" aria-label="Staff"><button className="on"><IconListCheck />My tasks</button><button><IconBell />Updates</button><button><IconUser />Me</button></nav>
  </>;
}

function TaskDetail({ q, me, role, back }: { q: Request; me: string; role: Role; back: () => void }) {
  const { db, advance, setBlock } = useStore();
  const [r, setR] = useState<WriteResult | null>(null);
  const [cant, setCant] = useState(false); const [why, setWhy] = useState("");
  const [release, setRelease] = useState(false);
  const room = db.rooms.find(x => x.id === q.roomId)!; const v = roomView(room, db);
  const arr = db.reservations.find(x => x.roomId === q.roomId && x.status === "confirmed" && x.arrivalDay === 0);
  const act = async (to: Request["status"], note?: string) => setR(await advance(q.id, to, me, note));
  const isBlockTask = q.kind === "maintenance" && !!room.block;
  const next = q.status === "assigned" || q.status === "received" ? { to: "acknowledged" as const, l: "Accept task" } : q.status === "acknowledged" ? { to: "in_progress" as const, l: q.kind === "turnover" ? "Start cleaning" : "I'm on my way" } : q.status === "in_progress" ? { to: "resolved" as const, l: q.kind === "turnover" ? "Cleaning done" : isBlockTask ? "Repair done" : "Mark done" } : null;
  return <>
    <Top title={`Room ${q.roomId}`} sub={`${typeOf(room.typeId).name}, floor ${room.floor}`} back={back} />
    <Offline />
    <div className="m-scroll">
      <div style={{ padding: 16, background: "var(--surface)", borderBottom: "1px solid var(--line)", display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}><ReqChip s={q.status} />{q.priority === "urgent" && isOpen(q) && <span className="chip s-urgent">Urgent</span>}<span className="chip s-neutral mono" style={{ fontFamily: "var(--mono)" }}>{q.ref}</span></div>
        <h2 className="h-page" style={{ fontSize: 20 }}>{q.title}</h2>
        {q.kind === "guest" ? <div className="note" style={{ margin: 0 }}>“{q.detail}”<div className="cap" style={{ marginTop: 4 }}>{q.guestFirst ? `${q.guestFirst}, ` : ""}via {q.channel}</div></div> : <div className="ink2">{q.detail}</div>}
        {arr && q.kind === "turnover" && <div className="alert info"><IconInfoCircle /><div>A guest arrives at <b>{arr.eta}</b>. Clean this room first.</div></div>}
        {v.stay && q.kind !== "turnover" && <div className="cap">Guest is in the room. Knock and wait before entering.</div>}
        <Sla q={q} />
      </div>
      <div className="m-sec">Timeline</div>
      <div style={{ padding: "0 16px 16px" }} className="steps-v">{q.history.map((h, i) => <div key={i} className={`sv${i < q.history.length - 1 || !isOpen(q) ? " done" : " now"}`}><i>{(i < q.history.length - 1 || !isOpen(q)) && <IconCheck />}</i><div style={{ paddingTop: 1 }}><div style={{ fontWeight: 500, fontSize: 14 }}>{h.text}</div><div className="cap num">{when(h.at)}{h.by ? ` · ${h.by}` : ""}</div></div></div>)}</div>
      <div style={{ padding: "0 16px 16px" }}><WriteAlert r={r} what="updated" conflict="Someone else updated this task a moment ago." /></div>
    </div>
    {cant ? <div className="m-foot"><b>What's stopping you?</b>{["Need parts or tools", "Guest asked me to come later", "This is for another team", "Something else"].map(w => <Opt key={w} radio on={why === w} onClick={() => setWhy(w)}>{w}</Opt>)}
      <div style={{ display: "flex", gap: 8 }}><button className="btn secondary touch" onClick={() => setCant(false)}>Back</button><SaveBtn size="touch" className="block" disabled={!why} onClick={async () => { await act("escalated", why); setCant(false); }}>Tell the front desk</SaveBtn></div></div>
    : release ? <div className="m-foot"><b>Is room {q.roomId} safe to sell?</b><span className="cap">Check the repair yourself. Releasing puts the room back on sale once it's cleaned.</span>
      <div style={{ display: "flex", gap: 8 }}><button className="btn secondary touch" onClick={() => setRelease(false)}>Keep blocked</button><SaveBtn size="touch" className="block" onClick={async () => { const x = await setBlock(q.roomId, undefined, me); setR(x); setRelease(false); }}>Release room</SaveBtn></div></div>
    : isOpen(q) ? <div className="m-foot">
      {next && <SaveBtn size="touch" className="block" onClick={async () => { await act(next.to); if (next.to === "resolved" && isBlockTask) setRelease(true); }}>{next.l}</SaveBtn>}
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn secondary touch" style={{ flex: 1 }} onClick={() => setCant(true)}>Can't do it</button>
        {role === "maintenance" && !room.block && q.kind === "guest" && <SaveBtn kind="danger" size="touch" className="block" onClick={async () => setR(await setBlock(q.roomId, { kind: "oos", reason: `${q.title}, unsafe`, since: now(), by: me, taskId: q.id }, me))}>Block room</SaveBtn>}
      </div></div>
    : isBlockTask ? <div className="m-foot"><button className="btn primary touch block" onClick={() => setRelease(true)}>Release room {q.roomId}</button></div>
    : <div className="m-foot"><span className="cap" style={{ textAlign: "center" }}>Done. The guest and front desk can see this.</span></div>}
  </>;
}

function Supervisor() {
  const { db, setHK } = useStore();
  const [r, setR] = useState<WriteResult | null>(null);
  const rooms = db.rooms.filter(x => x.hk === "clean" && !x.block && !roomView(x, db).stay);
  return <>
    <Top title="Inspections" sub={`${STAFF.supervisor} · Housekeeping supervisor`} />
    <Offline />
    <div className="m-scroll">
      <div className="m-sec">Cleaned, waiting for your check · {rooms.length}</div>
      <div style={{ padding: "0 16px" }}><WriteAlert r={r} what="updated" /></div>
      {rooms.length ? <div className="m-card">{rooms.map(x => { const arr = db.reservations.find(a => a.roomId === x.id && a.status === "confirmed" && a.arrivalDay === 0); return (
        <div key={x.id} className="m-row" style={{ flexWrap: "wrap" }}>
          <span style={{ fontFamily: "var(--head)", fontWeight: 700, fontSize: 22, width: 52 }}>{x.id}</span>
          <span style={{ flex: 1 }}><b style={{ fontWeight: 600 }}>{typeOf(x.typeId).name}</b><span className="cap" style={{ display: "block" }}>{arr ? `Guest arriving ${arr.eta}` : "No arrival today"}</span></span>
          <div style={{ display: "flex", gap: 8, width: "100%", paddingLeft: 64 }}>
            <SaveBtn kind="secondary" size="touch" className="block" onClick={async () => setR(await setHK(x.id, "dirty", STAFF.supervisor))}>Clean again</SaveBtn>
            <SaveBtn size="touch" className="block" onClick={async () => setR(await setHK(x.id, "inspected", STAFF.supervisor))}>Passed</SaveBtn>
          </div>
        </div>); })}</div> : <div className="muted" style={{ padding: "40px 24px", textAlign: "center" }}>No rooms waiting for inspection.</div>}
      <div className="cap" style={{ padding: 16 }}>Only supervisors see this list. A room marked Passed becomes Inspected, and the front desk can give it to a guest.</div>
    </div>
  </>;
}

// =====================================================================
// Guest: public booking request (WOR-41)
// =====================================================================
export function GuestBooking() {
  const { db, requestBooking } = useStore();
  const [s, setS] = useState<"list" | "room" | "form" | "done" | "status" | "status-code">("list");
  const [sref, setSref] = useState(""); const [sphone, setSphone] = useState("");
  const [arr, setArr] = useState(1); const [nights, setNights] = useState(2); const [adults, setAdults] = useState(2); const [typeId, setTypeId] = useState("dd");
  const [name, setName] = useState(""); const [phone, setPhone] = useState(""); const [note, setNote] = useState(""); const [consent, setConsent] = useState(false); const [tried, setTried] = useState(false);
  const [r, setR] = useState<WriteResult | null>(null);
  const t = typeOf(typeId); const free = (id: string) => eligibleRooms(db, { typeId: id, arrivalDay: arr, nights, adults }, false).ok.length;
  const digits = phone.replace(/\D/g, ""); const phoneOk = (digits.length === 11 && digits.startsWith("0")) || (digits.length === 13 && digits.startsWith("234"));
  if (s === "done" && r && (r.ok || r.kind === "duplicate")) return <><Top title="Request sent" /><div className="m-scroll" style={{ background: "var(--surface)", padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
    <div className="alert ok"><IconCircleCheck /><div><b>Your reference is <span className="mono">{r.ref}</span>.</b></div></div>
    <p>This is a <b>booking request</b>, not a confirmed booking yet. Reception checks the rooms and replies by SMS within 2 hours (8am–10pm).</p>
    <dl className="summary"><dt>Room</dt><dd>{t.name}</dd><dt>Dates</dt><dd>{day(arr)} to {day(arr + nights)}</dd><dt>Guests</dt><dd>{adults}</dd><dt>Estimated total</dt><dd>{naira(t.rate * nights)}</dd></dl>
    <p className="cap">No payment has been taken. You'll only pay once reception confirms. Questions? Call {"+234 1 555 0100"}.</p>
    <button className="btn secondary touch" onClick={() => { setS("list"); setR(null); }}>Done</button></div></>;
  if (s === "status") { const refOk = /^RMY-\d{4}$/i.test(sref.trim()); const ph = sphone.replace(/\D/g, ""); const phOk = (ph.length === 11 && ph.startsWith("0")) || (ph.length === 13 && ph.startsWith("234")); return <><Top title="Check a booking request" back={() => setS("list")} />
    <div className="m-scroll" style={{ background: "var(--surface)", padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
      <p className="ink2">Enter the reference from your text message and the mobile number you used. We'll text a code to that number before showing anything.</p>
      <div className="f"><label htmlFor="sr">Booking reference</label><input id="sr" className={`in${tried && !refOk ? " bad" : ""}`} style={{ height: 44 }} value={sref} onChange={e => setSref(e.target.value)} placeholder="RMY-1061" />{tried && !refOk && <span className="err">References look like RMY-1061.</span>}</div>
      <div className="f"><label htmlFor="sp">Mobile number</label><input id="sp" className={`in${tried && !phOk ? " bad" : ""}`} style={{ height: 44 }} value={sphone} onChange={e => setSphone(e.target.value)} inputMode="tel" placeholder="0803 555 0142" />{tried && !phOk && <span className="err">Enter a Nigerian mobile number.</span>}</div>
      <div className="cap" style={{ display: "flex", gap: 6 }}><IconLock size={14} style={{ flex: "none", marginTop: 1 }} />A reference alone never shows booking details.</div>
    </div>
    <div className="m-foot"><button className="btn primary touch block" onClick={() => { setTried(true); if (refOk && phOk) { setTried(false); setS("status-code"); } }}>Text me a code</button><span className="cap" style={{ textAlign: "center" }}>No text? Call reception on +234 1 555 0100.</span></div></>; }
  if (s === "status-code") return <><Top title="Check a booking request" back={() => setS("status")} />
    <div className="m-scroll" style={{ background: "var(--surface)", padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="alert info"><IconInfoCircle /><div>If <span className="mono">{sref.toUpperCase() || "RMY-1061"}</span> matches that number, a 6-digit code is on its way. It works for 10 minutes.</div></div>
      <div className="code" role="group" aria-label="6-digit code">{[0, 1, 2, 3, 4, 5].map(i => <input key={i} inputMode="numeric" maxLength={1} aria-label={`Digit ${i + 1}`} />)}</div>
      <div className="cap">Once verified you'll see whether reception has confirmed it. Nothing is confirmed until they do.</div>
    </div>
    <div className="m-foot"><button className="btn primary touch block" disabled>Show my request</button><button className="btn ghost touch">Send the code again</button></div></>;
  if (s === "form") return <><Top title="Your details" sub={`${t.name} · ${day(arr)}, ${nights} night${nights > 1 ? "s" : ""}`} back={() => setS("room")} />
    <div className="m-scroll" style={{ background: "var(--surface)", padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
      <WriteAlert r={r} what="booked" />
      <div className="f"><label htmlFor="bn">Full name</label><input id="bn" className={`in${tried && name.trim().split(/\s+/).length < 2 ? " bad" : ""}`} style={{ height: 44 }} value={name} onChange={e => setName(e.target.value)} autoComplete="name" />{tried && name.trim().split(/\s+/).length < 2 && <span className="err">Enter your first and last name.</span>}</div>
      <div className="f"><label htmlFor="bp">Mobile number</label><input id="bp" className={`in${tried && !phoneOk ? " bad" : ""}`} style={{ height: 44 }} value={phone} onChange={e => setPhone(e.target.value)} inputMode="tel" autoComplete="tel" placeholder="0803 555 0142" />{tried && !phoneOk ? <span className="err">Enter a Nigerian mobile number.</span> : <span className="help">We'll text you when reception confirms.</span>}</div>
      <div className="f"><label htmlFor="bnote">Anything we should know? (optional)</label><textarea id="bnote" className="in" rows={2} value={note} onChange={e => setNote(e.target.value)} placeholder="Late arrival, baby cot, quiet room…" /></div>
      <Opt on={consent} onClick={() => setConsent(v => !v)}><span style={{ fontSize: 14 }}>Text me about this booking</span><span className="cap" style={{ display: "block" }}>Only booking updates. See our privacy notice.</span></Opt>
      {tried && !consent && <span className="err">We need to text you to confirm the booking.</span>}
    </div>
    <div className="m-foot"><div className="cap" style={{ textAlign: "center" }}>Estimated {naira(t.rate * nights)}. Nothing to pay now.</div><SaveBtn size="touch" className="block" onClick={async () => { setTried(true); if (name.trim().split(/\s+/).length < 2 || !phoneOk || !consent) return; const x = await requestBooking({ name: name.trim(), phone, typeId, arrivalDay: arr, nights, adults, note }); setR(x); if (x.ok || x.kind === "duplicate") setS("done"); }}>Send booking request</SaveBtn></div></>;
  if (s === "room") { const n = free(typeId); return <><Top title={t.name} back={() => setS("list")} />
    <div className="m-scroll" style={{ background: "var(--surface)" }}>
      <div className="photo" style={{ height: 210 }}>Room photo (supplied by hotel)</div>
      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        <div><span className="h-page" style={{ fontSize: 22 }}>{naira(t.rate)}</span><span className="muted"> a night</span></div>
        <div className="ink2">Sleeps {t.capacity}. Air conditioning, Wi-Fi, work desk, rain shower. Breakfast 6:30–10:30.</div>
        <dl className="summary"><dt>Dates</dt><dd>{day(arr)} to {day(arr + nights)}</dd><dt>Guests</dt><dd>{adults}</dd><dt>Estimated total</dt><dd>{naira(t.rate * nights)}</dd></dl>
        {n > 0 ? <div className="alert info"><IconInfoCircle /><div><b>Looks available</b> for these dates. Rooms aren't held until reception confirms your request.</div></div> : <div className="alert warn"><IconAlertTriangle /><div><b>Probably full on these dates.</b> You can still ask, or call us on +234 1 555 0100 for other options.</div></div>}
        {adults > t.capacity && <div className="alert err"><IconAlertTriangle /><div>This room sleeps {t.capacity}. Choose a Family Suite for {adults} guests.</div></div>}
      </div>
    </div>
    <div className="m-foot"><button className="btn primary touch block" disabled={adults > t.capacity} onClick={() => setS("form")}>Request this room</button></div></>; }
  return <><Top title={HOTEL.name} sub="Lagos · Book directly" />
    <div className="m-scroll">
      <div style={{ padding: 16, background: "var(--surface)", borderBottom: "1px solid var(--line)", display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="f"><span className="lbl">Arrival</span><div className="hscroll" style={{ display: "flex", gap: 6, overflowX: "auto" }}>{[0, 1, 2, 3, 4, 5].map(d => <button key={d} className={`btn sm ${arr === d ? "primary" : "secondary"}`} onClick={() => setArr(d)} style={{ height: 40 }}>{d === 0 ? "Today" : day(d).replace(",", "")}</button>)}</div></div>
        <div className="row2"><div className="f"><span className="lbl">Nights</span><Stepper value={nights} set={setNights} min={1} max={14} label="nights" /></div><div className="f"><span className="lbl">Guests</span><Stepper value={adults} set={setAdults} min={1} max={4} label="guests" /></div></div>
      </div>
      <div className="m-sec">Rooms</div>
      <div className="m-card">{ROOM_TYPES.map(rt => { const n = free(rt.id); const fits = adults <= rt.capacity; return (
        <button key={rt.id} className="m-row" onClick={() => { setTypeId(rt.id); setS("room"); }} disabled={!fits} style={{ opacity: fits ? 1 : .5 }}>
          <span className="photo" style={{ width: 72, height: 56, borderRadius: 6, fontSize: 10 }}>Photo</span>
          <span style={{ flex: 1 }}><b style={{ fontWeight: 600 }}>{rt.name}</b><span className="cap" style={{ display: "block" }}>Sleeps {rt.capacity}{!fits ? " · too small for your group" : n ? " · looks available" : " · probably full"}</span><span className="num" style={{ fontWeight: 600 }}>{naira(rt.rate)}</span><span className="cap"> a night</span></span>
          <IconChevronRight size={18} color="var(--text-4)" />
        </button>); })}</div>
      <div className="cap" style={{ padding: 16 }}>Prices are per room per night, set by the hotel. Booking requests are confirmed by reception.</div>
      <div style={{ padding: "0 16px 16px" }}><button className="btn secondary touch block" onClick={() => { setTried(false); setS("status"); }}>Already asked? Check your request</button></div>
    </div></>;
}

// =====================================================================
// Guest: room QR → verify with invite code → My Stay → request → track (WOR-42)
// =====================================================================
export function GuestStay({ roomId = "204" }: { roomId?: string }) {
  const { db, createRequest, advance } = useStore();
  const stay = db.stays.find(s => s.roomId === roomId && s.status === "in_house");
  const guest = stay ? db.guests.find(g => g.id === stay.guestId) : undefined;
  const [s, setS] = useState<"qr" | "home" | "new" | "review" | "track">("qr");
  const [code, setCode] = useState(["", "", "", "", "", ""]); const [err, setErr] = useState<"" | "wrong" | "expired">(""); const [tries, setTries] = useState(3);
  const [cat, setCat] = useState<Dept>("Housekeeping"); const [text, setText] = useState("");
  const [r, setR] = useState<WriteResult | null>(null); const [tid, setTid] = useState<string | null>(null);
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const mine = db.requests.filter(q => q.roomId === roomId && q.kind === "guest" && (!stay || q.createdAt >= stay.arrivedAt)).sort((a, b) => b.createdAt - a.createdAt);
  const verify = () => { const c = code.join(""); if (c === "000000") { setErr("expired"); return; } if (c === "482913") { setS("home"); setErr(""); return; } setErr("wrong"); setTries(t => Math.max(0, t - 1)); };
  if (!stay && s !== "qr") return <><Top title={`Room ${roomId}`} /><div className="m-scroll" style={{ background: "var(--surface)", padding: 24 }}><div className="alert neutral"><IconLock /><div><b>This stay has ended.</b> Thank you for staying with us. The link no longer opens any details.</div></div></div></>;

  if (s === "qr") return <><Top title={HOTEL.name} sub={`Room ${roomId}`} />
    <div className="m-scroll" style={{ background: "var(--surface)", padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
      <div><h2 className="h-page">Welcome to room {roomId}</h2><p className="ink2" style={{ marginTop: 6 }}>To see your stay or ask for anything, enter the 6-digit code from your check-in text message.</p></div>
      <div className="code" role="group" aria-label="6-digit code">{code.map((d, i) => <input key={i} ref={el => { refs.current[i] = el; }} value={d} inputMode="numeric" maxLength={1} aria-label={`Digit ${i + 1}`} onChange={e => { const v = e.target.value.replace(/\D/g, "").slice(-1); setCode(c => { const n = [...c]; n[i] = v; return n; }); setErr(""); if (v && i < 5) refs.current[i + 1]?.focus(); }} onKeyDown={e => { if (e.key === "Backspace" && !code[i] && i > 0) refs.current[i - 1]?.focus(); }} />)}</div>
      {err === "wrong" && (tries > 0 ? <div className="alert err"><IconAlertTriangle /><div>That code doesn't match. {tries} tr{tries === 1 ? "y" : "ies"} left before it locks for 10 minutes.</div></div> : <div className="alert err"><IconLock /><div><b>Locked for 10 minutes.</b> Too many wrong codes. Ask the front desk for help, or dial 0 from the room phone.</div></div>)}
      {err === "expired" && <div className="alert warn"><IconAlertTriangle /><div><b>This code has expired.</b> Codes last 24 hours. Ask the front desk for a new one, or dial 0 from the room phone.</div></div>}
      <button className="btn primary touch block" disabled={code.join("").length < 6 || tries === 0} onClick={verify}>Open my stay</button>
      <div className="cap" style={{ display: "flex", gap: 6 }}><IconLock size={14} style={{ flex: "none", marginTop: 1 }} />The room code alone doesn't show any guest details. Prototype codes: 482913 works, 000000 is expired.</div>
      <div className="note" style={{ margin: 0 }}><b>No code?</b> Dial 0 from the room phone or come to reception. Breakfast is 6:30–10:30 on the ground floor.</div>
    </div></>;

  if (s === "track" && tid) { const q = db.requests.find(x => x.id === tid); if (q) { const steps = ["Received", "Sent to " + q.dept.toLowerCase(), q.dept === "Housekeeping" ? "On the way" : "Being handled", "Done"]; const at = q.status === "received" ? 0 : q.status === "assigned" || q.status === "acknowledged" ? 1 : q.status === "in_progress" ? 2 : q.status === "resolved" ? 3 : 1;
    return <><Top title={q.title} sub={q.ref} back={() => setS("home")} />
      <div className="m-scroll" style={{ background: "var(--surface)", padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
        {q.status === "escalated" && <div className="alert info"><IconInfoCircle /><div>The front desk is sorting this out and will update you here.</div></div>}
        <div className="steps-v">{steps.map((l, i) => <div key={l} className={`sv${i < at || q.status === "resolved" ? " done" : i === at ? " now" : ""}`}><i>{(i < at || q.status === "resolved") && <IconCheck />}</i><div style={{ paddingTop: 1 }}><div style={{ fontWeight: i === at ? 600 : 400, color: i > at ? "var(--text-3)" : undefined }}>{l}</div>{i === at && q.status !== "resolved" && <div className="cap">Asked {hhmm(q.createdAt)}. Usually takes about {q.targetMin} minutes.</div>}</div></div>)}</div>
        <div className="note" style={{ margin: 0 }}>“{q.detail}”</div>
        {q.status === "resolved" && <SaveBtn kind="secondary" size="touch" onClick={async () => { await advance(q.id, "received", "Guest", "Reopened: not fixed"); }}>It's not sorted, reopen</SaveBtn>}
      </div></>; } }

  if (s === "new" || s === "review") { const opts: Record<Dept, string[]> = { Housekeeping: ["Extra towels", "Clean my room", "Extra pillows", "Toiletries"], Maintenance: ["AC isn't cooling", "No hot water", "Light not working", "TV not working"], "Food & drink": ["Drinking water", "Room service menu", "Breakfast in room"], "Front desk": ["Late checkout", "Taxi to the airport", "Talk to someone"] };
    return <><Top title={cat} sub={`Room ${roomId}`} back={() => setS(s === "review" ? "new" : "home")} />
      <div className="m-scroll" style={{ background: "var(--surface)", padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
        {s === "new" ? <><div className="f"><span className="lbl">What do you need?</span><div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>{opts[cat].map(o => <button key={o} className={`qchip${text === o ? " on" : ""}`} style={text === o ? { boxShadow: "inset 0 0 0 1.5px var(--navy)", background: "var(--navy-soft)" } : undefined} onClick={() => setText(o)}>{o}</button>)}</div></div>
          <div className="f"><label htmlFor="gt">Or tell us in your own words</label><textarea id="gt" className="in" rows={3} value={text} onChange={e => setText(e.target.value)} style={{ fontSize: 15 }} /></div></>
        : <><WriteAlert r={r} what="sent" /><dl className="summary"><dt>Send to</dt><dd>{cat}</dd><dt>Room</dt><dd>{roomId}</dd><dt>Request</dt><dd>{text}</dd><dt>Usually takes</dt><dd>{triage(text).targetMin} min</dd></dl><div className="cap">Staff see your first name and room number only.</div></>}
      </div>
      <div className="m-foot">{s === "new" ? <button className="btn primary touch block" disabled={text.trim().length < 3} onClick={() => setS("review")}>Review</button>
        : <SaveBtn size="touch" className="block" onClick={async () => { const x = await createRequest({ roomId, guestFirst: guest?.name.split(" ")[0], text: text.trim(), channel: "Chat", dept: cat, title: text.length < 40 ? text : undefined }); setR(x); if ((x.ok || x.kind === "duplicate") && x.req) { setTid(x.req.id); setText(""); setS("track"); } }}>Send request</SaveBtn>}</div></>; }

  return <><Top title={`Room ${roomId}`} sub={`${guest?.name.split(" ")[0]}, until ${day(stay!.departDay)} 11:00`} right={<span className="chip s-insp noswatch" style={{ paddingLeft: 7 }}><IconLock size={12} />Verified</span>} />
    <div className="m-scroll">
      <div className="m-sec">Ask for something</div>
      <div className="m-card">{(["Housekeeping", "Maintenance", "Food & drink", "Front desk"] as Dept[]).map(d => <button key={d} className="m-row" onClick={() => { setCat(d); setText(""); setR(null); setS("new"); }}><span style={{ flex: 1 }}><b style={{ fontWeight: 600 }}>{d}</b><span className="cap" style={{ display: "block" }}>{d === "Housekeeping" ? "Towels, cleaning, pillows" : d === "Maintenance" ? "AC, water, lights, TV" : d === "Food & drink" ? "Water, room service" : "Checkout, taxi, questions"}</span></span><IconChevronRight size={18} color="var(--text-4)" /></button>)}</div>
      <div className="m-sec">Your requests</div>
      {mine.length ? <div className="m-card">{mine.slice(0, 4).map(q => <button key={q.id} className="m-row" onClick={() => { setTid(q.id); setS("track"); }}><span style={{ flex: 1 }}><b style={{ fontWeight: 600 }}>{q.title}</b><span style={{ display: "flex", gap: 8, marginTop: 4 }}><ReqChip s={q.status} /><span className="cap">{hhmm(q.createdAt)}</span></span></span><IconChevronRight size={18} color="var(--text-4)" /></button>)}</div> : <div className="cap" style={{ padding: "0 16px" }}>Nothing yet.</div>}
      <div className="m-sec">Your stay</div>
      <div className="m-card"><div className="m-row"><span style={{ flex: 1 }}>Check-out</span><span className="ink2">{day(stay!.departDay)}, {HOTEL.checkOut}</span></div><div className="m-row"><span style={{ flex: 1 }}>Wi-Fi</span><span className="mono">IkoyiCourt-Guest</span></div><div className="m-row"><span style={{ flex: 1 }}>Front desk</span><span className="ink2"><IconPhone size={14} style={{ verticalAlign: -2 }} /> Dial 0</span></div></div>
    </div>
    <nav className="m-tabs"><button className="on"><IconHome />My stay</button><button><IconMessageCircle />Ask Roomay</button><button><IconInfoCircle />Hotel</button></nav></>;
}

// =====================================================================
// Guest: Ask Roomay chat + voice + human handoff (WOR-43)
// =====================================================================
interface Msg { id: number; who: "me" | "bot" | "staff"; text?: string; card?: { text: string; dept: Dept; title: string; target: number; saved?: string; reqId?: string } }
export function GuestChat({ roomId = "204" }: { roomId?: string }) {
  const { createRequest } = useStore();
  const [msgs, setMsgs] = useState<Msg[]>([{ id: 1, who: "bot", text: "Hello Ada. I'm Roomay, the Ikoyi Court assistant. Tell me what you need and I'll send it to the right team. You can also ask for a person at any time." }]);
  const [text, setText] = useState(""); const [busy, setBusy] = useState(false); const [human, setHuman] = useState(false);
  const [mic, setMic] = useState<"off" | "ask" | "listening" | "review">("off"); const [partial, setPartial] = useState("");
  const [r, setR] = useState<WriteResult | null>(null);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs, busy, mic]);
  const add = (m: Omit<Msg, "id">) => setMsgs(x => [...x, { ...m, id: Date.now() + Math.random() }]);
  const send = (t: string) => {
    if (!t.trim()) return; add({ who: "me", text: t.trim() }); setText("");
    if (human) { setTimeout(() => add({ who: "staff", text: "Thanks, I'm on it. Amaka" }), 1400); return; }
    setBusy(true);
    setTimeout(async () => {
      setBusy(false); const tr = triage(t);
      if (/person|human|someone|reception/.test(t.toLowerCase()) || tr.sensitive === "payment") { setHuman(true); add({ who: "bot", text: tr.sensitive === "payment" ? "Billing questions are handled by a person, so I've passed this to the front desk. I won't change any charges. Amaka will reply here." : "Of course. Amaka at the front desk will reply here. I'll stay quiet until she's done." }); await createRequest({ roomId, guestFirst: "Ada", text: t.trim(), channel: "Chat", dept: "Front desk", title: tr.sensitive === "payment" ? "Billing question" : "Wants to speak to someone" }); return; }
      if (tr.sensitive === "safety") { add({ who: "bot", text: "If anyone is in danger, call the front desk now on 0, or leave the room. I've alerted the duty manager." }); await createRequest({ roomId, guestFirst: "Ada", text: t.trim(), channel: "Chat", dept: "Front desk", title: "Urgent safety issue" }); return; }
      if (tr.sensitive === "privacy") { add({ who: "bot", text: "Sorry, I can't share anything about other rooms or guests. The front desk can help with a message if needed." }); return; }
      if (!tr.confident) { add({ who: "bot", text: "I'm not sure which team handles that, so I've passed it to the front desk instead of guessing. They'll reply here." }); await createRequest({ roomId, guestFirst: "Ada", text: t.trim(), channel: "Chat", dept: "Front desk" }); return; }
      add({ who: "bot", card: { text: t.trim(), dept: tr.dept, title: tr.title, target: tr.targetMin } });
    }, 900);
  };
  const confirm = async (id: number) => {
    const m = msgs.find(x => x.id === id)!; const x = await createRequest({ roomId, guestFirst: "Ada", text: m.card!.text, channel: mic === "off" ? "Chat" : "Voice" }); setR(x);
    if ((x.ok || x.kind === "duplicate") && x.req) setMsgs(ms => ms.map(y => y.id === id ? { ...y, card: { ...y.card!, saved: x.req!.ref, reqId: x.req!.id } } : y));
  };
  const startMic = () => { setMic("listening"); setPartial(""); const words = "The AC in my room is blowing warm air".split(" "); words.forEach((w, i) => setTimeout(() => setPartial(p => (p ? p + " " : "") + w), 250 * (i + 1))); setTimeout(() => setMic("review"), 250 * (words.length + 2)); };
  return <>
    <Top title="Ask Roomay" sub={human ? "Front desk is replying · Roomay paused" : `Room ${roomId} · verified`} right={!human ? <button className="btn secondary sm" onClick={() => send("I'd like to talk to a person")}>Talk to a person</button> : undefined} />
    <div className="m-scroll" style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
      {msgs.map(m => m.text ? <div key={m.id} className={`bubble ${m.who === "me" ? "me" : "them"}`}>{m.who === "staff" && <div className="cap" style={{ marginBottom: 2 }}>Amaka, front desk</div>}{m.text}</div>
        : m.card ? <div key={m.id} className="bubble them" style={{ maxWidth: "92%" }}>
          <div>I'll send this to <b>{m.card.dept}</b> for room {roomId}. It usually takes about {m.card.target} minutes.</div>
          <dl className="summary" style={{ marginTop: 8, background: "var(--surface)" }}><dt>Request</dt><dd>{m.card.title}</dd><dt>Room</dt><dd>{roomId}</dd></dl>
          {m.card.saved ? <ChatStatus id={m.card.reqId!} refId={m.card.saved} /> : <><div style={{ marginTop: 8 }}><WriteAlert r={r} what="sent" /></div><div style={{ display: "flex", gap: 8, marginTop: 8 }}><SaveBtn size="sm" className="block" onClick={() => confirm(m.id)}>Send request</SaveBtn><button className="btn secondary sm" onClick={() => { setText(m.card!.text); setMsgs(ms => ms.filter(y => y.id !== m.id)); }}>Change</button></div></>}
        </div> : null)}
      {busy && <div className="bubble them cap" aria-label="Roomay is thinking">Roomay is reading your message…</div>}
      <div ref={end} />
    </div>
    {mic === "ask" && <div className="m-foot"><b>Allow microphone?</b><span className="cap">Roomay turns what you say into text. You'll check it before anything is sent. Nothing is recorded.</span><div style={{ display: "flex", gap: 8 }}><button className="btn secondary touch" style={{ flex: 1 }} onClick={() => setMic("off")}>Type instead</button><button className="btn primary touch" style={{ flex: 1 }} onClick={startMic}>Allow</button></div></div>}
    {mic === "listening" && <div className="m-foot"><div style={{ display: "flex", alignItems: "center", gap: 8 }}><span className="chip s-oos">Listening</span><span className="cap">Speak now. Tap Stop when you're done.</span></div><div style={{ minHeight: 44, fontSize: 16 }}>{partial || <span className="muted">…</span>}</div><button className="btn secondary touch" onClick={() => setMic("review")}>Stop</button></div>}
    {mic === "review" && <div className="m-foot"><span className="cap">Check what we heard. You can edit it.</span><textarea className="in" rows={2} value={partial} onChange={e => setPartial(e.target.value)} style={{ fontSize: 15 }} /><div style={{ display: "flex", gap: 8 }}><button className="btn secondary touch" onClick={startMic}>Say again</button><button className="btn primary touch" style={{ flex: 1 }} onClick={() => { send(partial); setMic("off"); }}>Send</button></div></div>}
    {mic === "off" && <>
      {!human && <div className="qchips">{["Two more towels", "Drinking water", "Late checkout?", "Wi-Fi password"].map(c => <button key={c} className="qchip" onClick={() => send(c === "Wi-Fi password" ? "What is the wifi password" : c === "Late checkout?" ? "Can I have a late checkout tomorrow?" : c === "Drinking water" ? "Can I get two bottles of drinking water" : "Please can I get two more towels")}>{c}</button>)}</div>}
      <div className="composer"><button className="round mic" onClick={() => setMic("ask")} aria-label="Speak instead of typing"><IconMicrophone /></button><textarea rows={1} value={text} onChange={e => setText(e.target.value)} placeholder={human ? "Message the front desk" : "Message Roomay"} aria-label="Message" onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }} /><button className="round send" disabled={!text.trim()} onClick={() => send(text)} aria-label="Send"><IconSend /></button></div>
    </>}
  </>;
}
function ChatStatus({ id, refId }: { id: string; refId: string }) {
  const { db } = useStore(); const q = db.requests.find(x => x.id === id);
  return <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}><span className="cap" style={{ color: "var(--insp)", display: "flex", gap: 4, alignItems: "center" }}><IconCheck size={14} />Saved as <span className="mono">{refId}</span></span>{q && <span style={{ display: "flex", gap: 8, alignItems: "center" }}><ReqChip s={q.status} />{q.assignee && q.status !== "resolved" && <span className="cap">{q.assignee.split(" ")[0]} has it</span>}</span>}</div>;
}

// =====================================================================
// WhatsApp storyboard (future integration — not live, needs Meta approval)
// =====================================================================
export function WhatsAppStory() {
  const B = ({ me, children, t }: { me?: boolean; children: ReactNode; t: string }) => <div style={{ alignSelf: me ? "flex-end" : "flex-start", maxWidth: "84%", background: me ? "#D9FDD3" : "#fff", borderRadius: 10, padding: "7px 10px 5px", fontSize: 14.5, lineHeight: "20px", boxShadow: "0 1px 1px rgba(0,0,0,.06)" }}>{children}<div style={{ textAlign: "right", fontSize: 11, color: "#667781" }}>{t}</div></div>;
  return <>
    <div className="m-top" style={{ background: "#F0F2F5" }}><span className="avatar" style={{ background: "var(--ink)", color: "var(--gold)" }}>R</span><div style={{ flex: 1 }}><div style={{ fontWeight: 600 }}>{HOTEL.name}</div><div className="cap">Business account</div></div></div>
    <div className="alert warn" style={{ borderRadius: 0, borderWidth: "0 0 1px", fontSize: 12.5 }}><IconInfoCircle /><div><b>Future integration, not live.</b> Needs Meta Business approval and approved message templates. Messages after 24 hours use templates only.</div></div>
    <div className="m-scroll" style={{ background: "#EFE7DE", padding: 12, display: "flex", flexDirection: "column", gap: 6 }}>
      <B t="09:02">Good morning, Ikoyi Court Hotel. I'd like to message you about bookings and my stay. Reply STOP any time to stop.</B>
      <B me t="09:04">Hi, do you have a family room for Friday, 2 nights, 4 of us?</B>
      <B t="09:04">I can send a booking request to reception: Family Suite, Fri to Sun, 4 guests, {naira(160000)} a night. Shall I send it?</B>
      <B me t="09:05">Yes please</B>
      <B t="09:05">Sent. Your request is <b>RMY-1050</b>. It isn't confirmed yet. Reception will reply here by 11:00.</B>
      <div style={{ alignSelf: "center", fontSize: 12, color: "#54656F", background: "#fff", borderRadius: 6, padding: "3px 8px", margin: "6px 0" }}>Friday</div>
      <B me t="15:40">The AC in 312 isn't cooling</B>
      <B t="15:40">To keep your stay private, please enter the 6-digit code from your check-in text first.</B>
      <B me t="15:41">482913</B>
      <B t="15:41">Thanks, Ada. I've sent “AC isn't cooling, room 312” to maintenance: <b>TCK-231</b>. Usually 30 minutes.</B>
      <B me t="15:44">Can I talk to someone?</B>
      <B t="15:44">Amaka from the front desk will reply here. Roomay is paused.</B>
    </div>
    <div className="composer" style={{ background: "#F0F2F5" }}><div style={{ flex: 1, height: 44, borderRadius: 22, background: "#fff", display: "flex", alignItems: "center", padding: "0 16px", color: "#8696A0" }}>Message</div></div>
  </>;
}

