import { useState } from "react";
import { IconLayoutDashboard, IconUsers, IconSettings, IconCheck, IconMinus, IconPlus, IconLock, IconInfoCircle, IconCircleCheck, IconAlertTriangle } from "@tabler/icons-react";
import { useStore } from "./store";
import { HOTEL, STAFF, ROOM_TYPES, roomView, typeOf, isOpen, isLate, minsSince, hhmm, naira, type Dept } from "./data";
import { Avatar, Tabs, Sheet, SaveBtn, WriteAlert, ReqChip, Sla, Opt, Empty } from "./ui";
import type { WriteResult } from "./store";

type P = "overview" | "team" | "setup";
const NAV: { id: P; label: string; icon: typeof IconUsers }[] = [{ id: "overview", label: "Overview", icon: IconLayoutDashboard }, { id: "team", label: "Team and roles", icon: IconUsers }, { id: "setup", label: "Hotel setup", icon: IconSettings }];

export function Manager({ page }: { page: P }) {
  const { data } = useStore();
  const go = (p: P) => { window.location.hash = `#/manager/${p}`; };
  return <div className="shell">
    <aside className="side" aria-label="Main">
      <div className="side-brand"><span className="mark">R</span><span className="wordmark">ROOMAY</span></div>
      <div className="prop"><Avatar name="Ikoyi Court" size={26} /><span className="prop-txt" style={{ flex: 1, minWidth: 0 }}><b className="ellipsis">{HOTEL.name}</b><span style={{ fontSize: 12, color: "#8C94A3" }}>Manager</span></span></div>
      <nav className="nav">{NAV.map(n => <button key={n.id} className={`nav-i${page === n.id ? " on" : ""}`} onClick={() => go(n.id)} aria-current={page === n.id ? "page" : undefined}><n.icon /><span className="nav-t">{n.label}</span></button>)}</nav>
      <div className="nav-sec">Switch to</div>
      <nav className="nav" style={{ paddingTop: 0 }}><a className="nav-i" href="#/reception/today" style={{ textDecoration: "none" }}><IconLayoutDashboard /><span className="nav-t">Front desk</span></a></nav>
      <div className="side-foot"><Avatar name="Funmi Adebayo" /><span className="me-txt"><span style={{ display: "block", color: "#fff", fontSize: 13, fontWeight: 500 }}>Funmi Adebayo</span><span style={{ fontSize: 12, color: "#8C94A3" }}>General manager</span></span></div>
    </aside>
    <div className="work">
      <header className="top"><h1 className="h-page" style={{ fontSize: 18 }}>{NAV.find(n => n.id === page)!.label}</h1><span style={{ flex: 1 }} /><span className="source"><i /><span>Synthetic preview · not live data</span></span></header>
      <div className="body"><div className="scroll">{data === "empty" || page === "setup" ? <Setup empty={data === "empty"} /> : page === "team" ? <Team /> : <Overview />}</div></div>
    </div>
  </div>;
}

function Overview() {
  const { db, setBlock } = useStore();
  const [r, setR] = useState<WriteResult | null>(null); const [rel, setRel] = useState<string | null>(null);
  const stays = db.stays.filter(s => s.status === "in_house");
  const reqs = db.requests.filter(q => q.kind === "guest");
  const done = reqs.filter(q => q.status === "resolved");
  const mins = done.map(q => Math.max(1, Math.round((q.history[q.history.length - 1].at - q.createdAt) / 60000))).sort((a, b) => a - b);
  const median = mins.length ? mins[Math.floor(mins.length / 2)] : null;
  const blocked = db.rooms.filter(x => x.block);
  const dirty = db.rooms.filter(x => !x.block && x.hk === "dirty" && !roomView(x, db).stay);
  const teams: Dept[] = ["Housekeeping", "Maintenance", "Food & drink", "Front desk"];
  const urgent = db.requests.filter(q => isOpen(q) && (q.priority === "urgent" || q.status === "escalated"));
  const acRooms = [...new Set(db.requests.filter(q => isOpen(q) && /AC/.test(q.title)).map(q => q.roomId))].filter(x => x.startsWith("3")).sort();
  const K = (l: string, v: React.ReactNode, m: string, warn?: boolean) => <div className="kpi" style={{ cursor: "default" }}><span className="l">{l}</span><span className="v">{v}</span><span className={`m${warn ? " warn" : ""}`}>{m}</span></div>;
  return <div className="page">
    <div className="page-h"><div className="grow"><h2 className="h-big">Today at {HOTEL.short}</h2><div className="muted" style={{ marginTop: 2 }}>Built only from today's records. Trends appear once there are 14 days of history.</div></div></div>
    <section className="kpis" style={{ gridTemplateColumns: "repeat(6, minmax(0,1fr))" }}>
      {K("Occupied tonight", <>{stays.length}<small> / {db.rooms.length}</small></>, `${Math.round(stays.length / db.rooms.length * 100)}%`)}
      {K("Open requests", reqs.filter(isOpen).length, `${reqs.filter(isLate).length} over target`, reqs.some(isLate))}
      {K("Median time to resolve", median ? `${median} min` : "—", median ? `${done.length} resolved today` : "No resolved requests yet")}
      {K("Rooms blocked", blocked.length, "Not for sale")}
      {K("Dirty and empty", dirty.length, "Cleaning backlog")}
      {K("Escalated or urgent", urgent.length, urgent.length ? "Needs a decision" : "None", urgent.length > 0)}
    </section>
    <div className="today-grid">
      <section className="box"><div className="box-h"><h3 className="h-sec grow">Requests by team, today</h3></div>
        <table className="tbl"><thead><tr><th>Team</th><th className="r">Open</th><th className="r">Over target</th><th className="r">Resolved</th><th>Target</th></tr></thead>
          <tbody>{teams.map(t => { const q = reqs.filter(x => x.dept === t); return <tr key={t}><td style={{ fontWeight: 500 }}>{t}</td><td className="r num">{q.filter(isOpen).length}</td><td className="r num" style={{ color: q.some(isLate) ? "var(--urgent)" : undefined, fontWeight: q.some(isLate) ? 600 : 400 }}>{q.filter(isLate).length}</td><td className="r num">{q.filter(x => x.status === "resolved").length}</td><td className="muted">{t === "Housekeeping" ? "15 min" : t === "Maintenance" ? "30 min" : t === "Food & drink" ? "25 min" : "10 min"}</td></tr>; })}</tbody></table>
        <div className="box-h" style={{ borderTop: "1px solid var(--line)" }}><h3 className="h-sec grow">Repeat problems</h3><span className="cap">Last 24 hours</span></div>
        <div style={{ padding: 16 }}>{acRooms.length >= 2 ? <div className="alert info"><span className="roomay-tag" style={{ marginTop: 2 }}>ROOMAY</span><div><b>AC problems in {acRooms.length} rooms on floor 3</b> ({acRooms.join(", ")}). Could be one shared cause. Ask maintenance to inspect the floor's AC supply and log it as one incident.</div></div> : <div className="muted">No repeating problems found today.</div>}
          <div className="cap" style={{ marginTop: 10 }}>Roomay groups reports by room, floor and problem type. It only flags patterns it can see in real records. It never estimates.</div></div>
      </section>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <section className="box"><div className="box-h"><h3 className="h-sec grow">Blocked rooms</h3></div>
          <div className="divide">{blocked.map(x => <div key={x.id} style={{ padding: "12px 16px", display: "flex", gap: 10, alignItems: "flex-start" }}>
            <span className="roomno" style={{ width: 36 }}>{x.id}</span>
            <div style={{ flex: 1 }}><span className={`chip s-${x.block!.kind}`}>{x.block!.kind === "oos" ? "Out of service" : "Out of order"}</span><div style={{ marginTop: 4 }}>{x.block!.reason}</div><div className="cap">By {x.block!.by} at {hhmm(x.block!.since)}{x.block!.until ? `, until ${x.block!.until}` : ""}</div></div>
            <button className="btn secondary sm" onClick={() => setRel(x.id)}>Release</button></div>)}
            {!blocked.length && <div className="muted" style={{ padding: 16 }}>No rooms are blocked.</div>}</div>
          <div style={{ padding: "0 16px 12px" }}><WriteAlert r={r} what="released" /><div className="cap" style={{ marginTop: 6 }}>Releasing confirms the repair was checked. The room still needs cleaning before it's sold.</div></div>
        </section>
        {rel && <Release roomId={rel} close={() => setRel(null)} done={x => { setR(x); if (x.ok) setRel(null); }} save={() => setBlock(rel, undefined, "Funmi Adebayo")} />}
        <section className="box"><div className="box-h"><h3 className="h-sec grow">Needs a manager</h3></div>
          <div className="divide">{urgent.map(q => <div key={q.id} style={{ padding: "12px 16px" }}><div style={{ display: "flex", gap: 8, alignItems: "center" }}><span className="roomno">{q.roomId}</span><b style={{ fontWeight: 500, flex: 1 }}>{q.title}</b><ReqChip s={q.status} /></div><div style={{ marginTop: 4 }}><Sla q={q} /></div></div>)}
            {!urgent.length && <div className="muted" style={{ padding: 16 }}>Nothing urgent.</div>}</div></section>
      </div>
    </div>
  </div>;
}

const ROLES = ["Receptionist", "Manager", "Housekeeping", "Supervisor", "Maintenance", "Food & drink", "Guest"];
const MATRIX: [string, string[]][] = [
  ["See today's arrivals and rooms", ["yes", "yes", "rooms", "rooms", "rooms", "no", "no"]],
  ["See guest phone numbers", ["logged", "logged", "no", "no", "no", "no", "own"]],
  ["Create walk-ins and confirm bookings", ["yes", "yes", "no", "no", "no", "no", "request"]],
  ["Check in and check out", ["yes", "yes", "no", "no", "no", "no", "no"]],
  ["Mark rooms Dirty or Clean", ["yes", "yes", "yes", "yes", "no", "no", "no"]],
  ["Mark rooms Inspected", ["no", "yes", "no", "yes", "no", "no", "no"]],
  ["Block a room (out of service)", ["yes", "yes", "no", "no", "yes", "no", "no"]],
  ["Release a blocked room", ["no", "yes", "no", "no", "yes", "no", "no"]],
  ["Work on requests", ["front desk", "yes", "own team", "own team", "own team", "own team", "own"]],
  ["Add rooms, staff and roles", ["no", "yes", "no", "no", "no", "no", "no"]],
];
const Cell = ({ v }: { v: string }) => v === "yes" ? <IconCheck size={16} color="var(--insp)" stroke={2.6} aria-label="Allowed" /> : v === "no" ? <IconMinus size={16} color="var(--text-4)" aria-label="Not allowed" /> : <span className="cap" style={{ color: "var(--text-2)" }}>{v === "logged" ? "Yes, logged" : v === "own" ? "Own stay only" : v === "rooms" ? "Room status only" : v === "request" ? "Request only" : v === "own team" ? "Own team only" : v}</span>;

function Team() {
  const [invite, setInvite] = useState(false); const [revoke, setRevoke] = useState<string | null>(null);
  const people: [string, string, string][] = [["Funmi Adebayo", "Manager", "Today 08:02"], [STAFF.reception, "Receptionist", "Now"], [STAFF.reception2, "Receptionist", "Now"], [STAFF.housekeeping, "Housekeeping", "Now"], [STAFF.supervisor, "Supervisor", "10:31"], [STAFF.maintenance, "Maintenance", "Now"], ["Kelechi Uba", "Food & drink", "Yesterday"]];
  return <div className="page">
    <div className="page-h"><div className="grow"><h2 className="h-big">Team and roles</h2><div className="muted" style={{ marginTop: 2 }}>People sign in with their own Workpeg account. Their role decides what they can see and do here.</div></div><button className="btn primary" onClick={() => setInvite(true)}><IconPlus />Invite someone</button></div>
    <section className="box" style={{ marginBottom: 16 }}><table className="tbl"><thead><tr><th>Name</th><th>Role</th><th>Last active</th><th className="r"></th></tr></thead>
      <tbody>{people.map(([n, r, a]) => <tr key={n}><td><span style={{ display: "inline-flex", gap: 10, alignItems: "center" }}><Avatar name={n} size={28} />{n}</span></td><td>{r}</td><td className="muted">{a}</td><td className="r">{r !== "Manager" && <button className="btn ghost sm" onClick={() => setRevoke(n)}>Remove access</button>}</td></tr>)}</tbody></table></section>
    <section className="box"><div className="box-h"><h3 className="h-sec grow">What each role can do</h3><span className="cap">Enforced by Workpeg permissions, not just hidden in the interface</span></div>
      <table className="tbl"><thead><tr><th>Action</th>{ROLES.map(r => <th key={r} style={{ textAlign: "center" }}>{r}</th>)}</tr></thead>
        <tbody>{MATRIX.map(([a, v]) => <tr key={a}><td style={{ fontWeight: 500 }}>{a}</td>{v.map((x, i) => <td key={i} style={{ textAlign: "center" }}><Cell v={x} /></td>)}</tr>)}</tbody></table></section>
    {invite && <Invite close={() => setInvite(false)} />}
    {revoke && <Revoke name={revoke} close={() => setRevoke(null)} />}
  </div>;
}
function Release({ roomId, close, save, done }: { roomId: string; close: () => void; save: () => Promise<WriteResult>; done: (r: WriteResult) => void }) {
  const { db } = useStore(); const room = db.rooms.find(x => x.id === roomId)!; const task = db.requests.find(q => q.id === room.block?.taskId || q.id === "q-" + roomId);
  const [ok, setOk] = useState(false); const [r, setR] = useState<WriteResult | null>(null);
  return <Sheet title={`Release room ${roomId}?`} sub={`${room.block?.kind === "oos" ? "Out of service" : "Out of order"} · ${room.block?.reason}`} onClose={close}
    footer={<><button className="btn ghost" onClick={close}>Keep blocked</button><span style={{ flex: 1 }} /><SaveBtn disabled={!ok} onClick={async () => { const x = await save(); setR(x); done(x); }}>Release room {roomId}</SaveBtn></>}>
    <WriteAlert r={r} what="released" />
    <div className="f"><span className="lbl">What happened</span><div className="steps-v">{(task?.history || [{ at: room.block!.since, text: `Blocked: ${room.block!.reason}`, by: room.block!.by }]).map((h, i) => <div key={i} className="sv done"><i><IconCheck /></i><div style={{ paddingTop: 1 }}><div style={{ fontWeight: 500 }}>{h.text}</div><div className="cap num">{hhmm(h.at)}{h.by ? ` · ${h.by}` : ""}</div></div></div>)}</div></div>
    {task && isOpen(task) && <div className="alert warn"><IconAlertTriangle /><div><b>The repair task is still open</b> ({task.ref}). Maintenance hasn't marked it done. Only release if you've seen the room yourself.</div></div>}
    <Opt on={ok} onClick={() => setOk(v => !v)}><b style={{ fontWeight: 500 }}>I've checked room {roomId} myself and it's safe for guests</b><span className="cap" style={{ display: "block" }}>Your name and the time are saved in the room's history.</span></Opt>
    <div className="cap">After release the room is <b>{room.hk === "dirty" ? "Dirty" : room.hk === "clean" ? "Clean" : "Inspected"}</b>{room.hk === "dirty" ? " and housekeeping gets a cleaning task. It isn't offered to guests until it's cleaned." : "."} Roomay never releases a room by itself.</div>
  </Sheet>;
}
function Revoke({ name, close }: { name: string; close: () => void }) {
  const { toast } = useStore();
  return <Sheet title={`Remove ${name.split(" ")[0]}'s access?`} sub={name} onClose={close}
    footer={<><button className="btn ghost" onClick={close}>Cancel</button><span style={{ flex: 1 }} /><SaveBtn kind="danger" onClick={async () => { await new Promise(r => setTimeout(r, 700)); toast({ title: `${name} can no longer open Roomay`, body: "Signed out on every device", tone: "info" }); close(); }}>Remove access</SaveBtn></>}>
    <dl className="summary"><dt>Signed out</dt><dd>Straight away, on every device</dd><dt>Their open tasks</dt><dd>Go back to the team queue, unassigned</dd><dt>History</dt><dd>Kept. Past check-ins and notes still show their name</dd></dl>
    <div className="alert neutral"><IconLock /><div>This removes their role in this hotel only. Their Workpeg account isn't deleted, and Roomay can't change their password.</div></div>
  </Sheet>;
}
function Invite({ close }: { close: () => void }) {
  const { toast } = useStore();
  const [name, setName] = useState(""); const [phone, setPhone] = useState(""); const [role, setRole] = useState("");
  return <Sheet title="Invite someone" sub="They'll get a text to join with their Workpeg account" onClose={close} footer={<><button className="btn ghost" onClick={close}>Cancel</button><span style={{ flex: 1 }} /><SaveBtn disabled={!name || !phone || !role} onClick={async () => { await new Promise(r => setTimeout(r, 600)); toast({ title: `Invite sent to ${name}`, body: `${role}. Access starts when they accept.`, tone: "ok" }); close(); }}>Send invite</SaveBtn></>}>
    <div className="f"><label htmlFor="in1">Full name</label><input id="in1" className="in" value={name} onChange={e => setName(e.target.value)} /></div>
    <div className="f"><label htmlFor="in2">Mobile number</label><input id="in2" className="in" value={phone} onChange={e => setPhone(e.target.value)} inputMode="tel" placeholder="0803 555 0142" /></div>
    <div className="f"><span className="lbl">Role</span>{ROLES.slice(0, 6).map(r => <Opt key={r} radio on={role === r} onClick={() => setRole(r)}><b style={{ fontWeight: 500 }}>{r}</b><span className="cap" style={{ display: "block" }}>{r === "Receptionist" ? "Front desk: bookings, check-in, rooms, requests" : r === "Manager" ? "Everything, including setup and roles" : r === "Supervisor" ? "Housekeeping plus room inspections" : `${r} tasks on their phone`}</span></Opt>)}</div>
    <div className="alert neutral"><IconLock /><div>Roomay can't create Workpeg accounts or passwords. The person accepts the invite with their own account.</div></div>
  </Sheet>;
}

function Setup({ empty }: { empty: boolean }) {
  const { db } = useStore(); const [tab, setTab] = useState<"types" | "rooms" | "teams">("types");
  const steps: [string, boolean][] = [["Hotel details", true], ["Room types", !empty], ["Rooms", !empty], ["Teams and staff", !empty], ["Check-in rules", false]];
  return <div className="page">
    <div className="page-h"><div className="grow"><h2 className="h-big">Hotel setup</h2><div className="muted" style={{ marginTop: 2 }}>Only managers can change these. Changes apply to the whole hotel straight away.</div></div></div>
    <section className="box" style={{ padding: 16, marginBottom: 16 }}><div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>{steps.map(([s, ok], i) => <div key={s} style={{ display: "flex", gap: 8, alignItems: "center" }}><span style={{ width: 22, height: 22, borderRadius: "50%", display: "grid", placeItems: "center", fontSize: 12, fontWeight: 600, background: ok ? "var(--insp-bg)" : "var(--sunken)", color: ok ? "var(--insp)" : "var(--text-3)", boxShadow: ok ? "none" : "inset 0 0 0 1px var(--line-2)" }}>{ok ? <IconCheck size={13} stroke={3} /> : i + 1}</span><span style={{ fontWeight: ok ? 400 : 500 }}>{s}</span></div>)}</div></section>
    {empty ? <section className="box"><Empty icon={<IconSettings />} title="Add your room types first" body="Start with the kinds of rooms you sell, for example Standard Queen or Family Suite, with the capacity and nightly rate. Then add each room number. Nothing is set up for you automatically." action={<button className="btn primary"><IconPlus />Add a room type</button>} /></section> : <>
      <section className="box">
        <Tabs value={tab} onChange={setTab} items={[{ v: "types", label: "Room types", n: ROOM_TYPES.length }, { v: "rooms", label: "Rooms", n: db.rooms.length }, { v: "teams", label: "Teams", n: 4 }]} />
        {tab === "types" && <table className="tbl"><thead><tr><th>Room type</th><th className="r">Sleeps</th><th className="r">Rate a night</th><th className="r">Rooms</th><th className="r"></th></tr></thead><tbody>{ROOM_TYPES.map(t => <tr key={t.id}><td style={{ fontWeight: 500 }}>{t.name}</td><td className="r num">{t.capacity}</td><td className="r num">{naira(t.rate)}</td><td className="r num">{db.rooms.filter(x => x.typeId === t.id).length}</td><td className="r"><button className="btn ghost sm">Edit</button></td></tr>)}</tbody></table>}
        {tab === "rooms" && <table className="tbl"><thead><tr><th>Room</th><th>Type</th><th>Floor</th><th>Features</th><th>Status</th></tr></thead><tbody>{db.rooms.slice(0, 14).map(x => <tr key={x.id}><td className="roomno">{x.id}</td><td>{typeOf(x.typeId).name}</td><td>{x.floor}</td><td className="muted">{x.features.join(", ")}</td><td>{x.block ? <span className={`chip s-${x.block.kind}`}>{x.block.kind === "oos" ? "Out of service" : "Out of order"}</span> : <span className="chip s-neutral">In use</span>}</td></tr>)}</tbody></table>}
        {tab === "teams" && <table className="tbl"><thead><tr><th>Team</th><th>Handles</th><th>Target time</th></tr></thead><tbody>{([["Housekeeping", "Towels, cleaning, bedding", "15 min"], ["Maintenance", "AC, plumbing, electrics, TV", "30 min"], ["Food & drink", "Water, room service", "25 min"], ["Front desk", "Questions, billing, anything unclear", "10 min"]] as const).map(([a, b, c]) => <tr key={a}><td style={{ fontWeight: 500 }}>{a}</td><td className="muted">{b}</td><td>{c}</td></tr>)}</tbody></table>}
      </section>
      <div className="alert info" style={{ marginTop: 16 }}><IconInfoCircle /><div><b>Check-in rules:</b> require supervisor inspection before a room is Ready? Currently <b>off</b>: Clean rooms can be given to guests.</div></div>
    </>}
  </div>;
}
void IconCircleCheck; void IconAlertTriangle; void minsSince;
