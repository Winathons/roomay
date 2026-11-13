import { useState, type ReactNode } from "react";
import { IconX, IconRefresh, IconLock, IconEye, IconShieldCheck } from "@tabler/icons-react";
import { useStore, resGuest, type WriteResult } from "../store";
import { roomView, typeOf, day, hhmm, when, now, naira, STAFF, eligibleRooms, type Dept } from "../data";
import { HKChip, BlockChip, OccChip, ReadyChip, ResChip, ReqChip, Sla, SaveBtn, WriteAlert, shortName, Opt } from "../ui";
import { useRec } from "./ctx";

export function Panel() {
  const { panel, show } = useRec();
  const close = () => show(null);
  return <aside className={`panel${panel ? " open" : ""}`} aria-label="Details" aria-hidden={!panel}><div className="panel-in">
    {panel?.t === "room" && <RoomP key={panel.id} id={panel.id} close={close} />}
    {panel?.t === "res" && <ResP key={panel.id} id={panel.id} close={close} />}
    {panel?.t === "req" && <ReqP key={panel.id} id={panel.id} close={close} />}
  </div></aside>;
}
function Head({ title, sub, chips, close }: { title: ReactNode; sub: ReactNode; chips?: ReactNode; close: () => void }) {
  return <div className="panel-h"><div style={{ flex: 1, minWidth: 0 }}><h2 className="h-page" style={{ fontSize: 20 }}>{title}</h2><div className="muted" style={{ marginTop: 2, fontSize: 13 }}>{sub}</div>{chips && <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>{chips}</div>}</div><button className="icon-btn" onClick={close} aria-label="Close panel"><IconX /></button></div>;
}

// ---------- room ----------
function RoomP({ id, close }: { id: string; close: () => void }) {
  const { db, setHK } = useStore(); const { open, show } = useRec();
  const room = db.rooms.find(r => r.id === id)!; const v = roomView(room, db); const t = typeOf(room.typeId);
  const [r, setR] = useState<WriteResult | null>(null);
  return <>
    <Head title={`Room ${room.id}`} sub={`${t.name}, floor ${room.floor}, sleeps ${t.capacity}`} chips={<><ReadyChip room={room} db={db} /><OccChip occ={v.occ} />{room.block ? <BlockChip room={room} /> : <HKChip hk={room.hk} />}</>} close={close} />
    <div className="panel-b">
      {room.block && <div style={{ padding: "0 16px" }}><div className={`alert ${room.block.kind === "oos" ? "err" : "warn"}`}><IconLock /><div><b>{room.block.kind === "oos" ? "Out of service" : "Out of order"}: {room.block.reason}.</b> Set by {room.block.by} at {hhmm(room.block.since)}{room.block.until ? `, until ${room.block.until}` : ""}. Roomay won't offer this room. Only maintenance or a manager can release it after checking the repair.</div></div></div>}
      <dl className="kv">
        <dt>Guest</dt><dd>{v.stay && v.guest ? <><span style={{ fontWeight: 500 }}>{v.guest.name}</span><span className="cap">{v.stay.departDay < 0 ? "Was due out yesterday" : v.stay.departDay === 0 ? "Leaves today, 11:00" : `Leaves ${day(v.stay.departDay)}`}</span></> : v.arrival && v.guest ? <><span style={{ fontWeight: 500 }}>{v.guest.name}</span><span className="cap">Arrives today, {v.arrival.eta}</span></> : <span className="muted">Empty</span>}</dd>
        <dt>Cleaning</dt><dd>{room.block ? <BlockChip room={room} /> : <HKChip hk={room.hk} />}<span className="cap">{room.hk === "dirty" ? (db.requests.some(q => q.roomId === id && q.kind === "turnover" && q.status === "in_progress") ? `${STAFF.housekeeping} is cleaning it now` : `Cleaning task with ${STAFF.housekeeping}`) : room.hk === "clean" ? "Cleaned, waiting for a supervisor check" : "Cleaned and checked"}</span></dd>
        <dt>Features</dt><dd>{room.features.join(", ")}</dd>
        <dt>Requests</dt><dd>{v.open.length ? v.open.map(q => <button key={q.id} className="btn ghost sm" style={{ marginLeft: -10 }} onClick={() => show({ t: "req", id: q.id })}>{q.title} · <Sla q={q} compact /></button>) : <span className="muted">None open</span>}</dd>
      </dl>
      {!room.block && !v.stay && <div style={{ padding: "0 16px 16px" }}>
        <div className="k" style={{ marginBottom: 6 }}>Set cleaning status</div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <SaveBtn kind="secondary" size="sm" disabled={room.hk === "dirty"} onClick={async () => setR(await setHK(id, "dirty", STAFF.reception))}>Dirty</SaveBtn>
          <SaveBtn kind="secondary" size="sm" disabled={room.hk === "clean"} onClick={async () => setR(await setHK(id, "clean", STAFF.reception))}>Clean</SaveBtn>
          <button className="btn secondary sm" disabled title="Only a housekeeping supervisor can mark a room Inspected">Inspected</button>
        </div>
        <div className="cap" style={{ marginTop: 6 }}>Only a housekeeping supervisor can mark a room Inspected.</div>
        <div style={{ marginTop: 8 }}><WriteAlert r={r} what="updated" /></div>
      </div>}
    </div>
    <div className="panel-f">
      {v.stay ? <><button className="btn secondary" onClick={() => show({ t: "res", id: v.stay!.resId })}>Open stay</button><button className="btn secondary" onClick={() => open({ t: "move", stayId: v.stay!.id })}>Move guest</button><button className="btn primary" onClick={() => open({ t: "checkout", stayId: v.stay!.id })}>Check out</button></>
        : v.arrival ? <><button className="btn secondary" onClick={() => show({ t: "res", id: v.arrival!.id })}>Open booking</button><button className={`btn ${v.ready ? "primary" : "secondary"}`} onClick={() => open({ t: "checkin", resId: v.arrival!.id })}>Check in</button></>
        : room.block ? <button className="btn secondary" onClick={() => room.block?.taskId && show({ t: "req", id: room.block.taskId })} disabled={!room.block.taskId}>View repair task</button>
        : <><button className="btn secondary" onClick={() => open({ t: "request", roomId: id })}>Report a problem</button>{v.ready && <button className="btn primary" onClick={() => open({ t: "walkin" })}>Walk-in</button>}</>}
    </div>
  </>;
}

// ---------- reservation / stay (booking ≠ stay) ----------
function ResP({ id, close }: { id: string; close: () => void }) {
  const { db, confirm, extend } = useStore(); const { open } = useRec();
  const res = db.reservations.find(x => x.id === id)!; const g = resGuest(db, res); const t = typeOf(res.typeId);
  const stay = db.stays.find(s => s.resId === id && s.status === "in_house");
  const [phone, setPhone] = useState(false);
  const [checkedAt, setCheckedAt] = useState(now());
  const avail = eligibleRooms(db, res, false);
  const [pick, setPick] = useState<string | undefined>(avail.ok[0]?.room.id);
  const [r, setR] = useState<WriteResult | null>(null);
  const [showOut, setShowOut] = useState(false);
  const total = res.rate * res.nights;
  return <>
    <Head title={shortName(g.name)} sub={<><span className="mono">{res.ref}</span> · via {res.source}</>} chips={<>{stay ? <span className={`chip s-${stay.departDay < 0 ? "urgent" : "house"}`}>{stay.departDay < 0 ? "Overdue" : "In house"}</span> : <ResChip s={res.status} />}{res.roomId && <span className="chip s-neutral">Room {res.roomId}</span>}</>} close={close} />
    <div className="panel-b">
      <dl className="kv">
        <dt>Dates</dt><dd><span>{day(res.arrivalDay)} to {day(res.arrivalDay + res.nights)}</span><span className="cap">{res.nights} night{res.nights > 1 ? "s" : ""}{res.arrivalDay === 0 && res.status !== "checked_in" ? `, arriving ${res.eta}` : ""}</span></dd>
        <dt>Room</dt><dd><span>{res.roomId ? `${res.roomId}, ${t.name}` : <span className="muted">Not assigned yet</span>}</span><span className="cap">Requested: {t.name}</span></dd>
        <dt>Guests</dt><dd><span>{res.adults} adult{res.adults > 1 ? "s" : ""}{res.occupants.length ? `: ${res.occupants.join(", ")}` : ""}</span><span className="cap">Room sleeps {t.capacity}</span></dd>
        <dt>Rate</dt><dd><span className="num">{naira(res.rate)} a night</span><span className="cap num">{naira(total)} total</span></dd>
        <dt>Balance</dt><dd>{stay ? (stay.amountDue ? <span className="num" style={{ fontWeight: 600 }}>{naira(stay.amountDue)} due</span> : <span>Settled</span>) : <span>{res.payment === "paid" ? "Paid in full" : res.payment === "deposit" ? "Deposit taken" : "Nothing paid yet"}</span>}<span className="cap">Recorded by staff. Roomay doesn't take payments.</span></dd>
        <dt>ID check</dt><dd>{res.idChecked ? <span>Checked at the desk</span> : <span className="muted">Not yet. Required at check-in</span>}</dd>
        <dt>Phone</dt><dd>{phone ? <span className="num">{g.phone}</span> : <button className="btn ghost sm" style={{ marginLeft: -10 }} onClick={() => setPhone(true)}><IconEye />Show phone number</button>}{phone && <span className="cap">Viewing is logged.</span>}</dd>
      </dl>
      {res.note && <div className="note">“{res.note}”</div>}

      {res.status === "pending" && <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}><IconShieldCheck size={18} color="var(--navy)" /><h3 className="h-sec" style={{ flex: 1 }}>Confirm against live rooms</h3><button className="btn ghost sm" onClick={() => setCheckedAt(now())}><IconRefresh />Recheck</button></div>
        <div className="cap">Availability checked at {hhmm(checkedAt)}. No room is held until you confirm.</div>
        <WriteAlert r={r} what="booked" conflict={`Another receptionist just booked room ${pick} for these dates.`} />
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }} role="radiogroup" aria-label="Room">
          {avail.ok.slice(0, 5).map((c, i) => <Opt key={c.room.id} radio on={pick === c.room.id} onClick={() => setPick(c.room.id)}><span style={{ display: "flex", gap: 8, alignItems: "center" }}><b style={{ fontWeight: 600 }}>Room {c.room.id}</b>{i === 0 && <span className="roomay-tag">BEST MATCH</span>}</span><span className="cap">{c.why.join(", ")}</span></Opt>)}
          {!avail.ok.length && <div className="alert warn"><IconLock /><div><b>No {t.name} is free for these dates.</b> Offer another room type, or decline the request politely.</div></div>}
        </div>
        {avail.out.length > 0 && <><button className="btn ghost sm" style={{ alignSelf: "flex-start", marginLeft: -10 }} onClick={() => setShowOut(v => !v)} aria-expanded={showOut}>{showOut ? "Hide" : "Show"} {avail.out.length} rooms that can't be used</button>
          {showOut && <div className="divide" style={{ border: "1px solid var(--line)", borderRadius: 6 }}>{avail.out.map(o => <div key={o.room.id} style={{ display: "flex", gap: 10, padding: "8px 10px", fontSize: 13 }}><span className="roomno" style={{ width: 32 }}>{o.room.id}</span><span className="ink2">{o.why}</span></div>)}</div>}</>}
      </div>}

      <div className="sec-h">Activity</div>
      <div className="log">{[...res.audit].reverse().map((h, i) => <div key={i} className="log-i"><time>{when(h.at)}</time><div>{h.text}{h.by && <span className="cap"> · {h.by}</span>}</div></div>)}</div>
    </div>
    <div className="panel-f">
      {res.status === "pending" && <><button className="btn danger" onClick={() => open({ t: "cancel", resId: id })}>Decline</button><span style={{ flex: 1 }} /><SaveBtn disabled={!pick} onClick={async () => { const x = await confirm(id, pick!); setR(x); if (!x.ok && x.kind === "conflict") { setCheckedAt(now()); setPick(undefined); } }}>Confirm in {pick || "…"}</SaveBtn></>}
      {res.status === "confirmed" && <><button className="btn danger" onClick={() => open({ t: "cancel", resId: id })}>Cancel booking</button><span style={{ flex: 1 }} /><button className="btn secondary" onClick={() => open({ t: "edit", resId: id })}>Change dates</button>{res.arrivalDay === 0 && <button className="btn primary" onClick={() => open({ t: "checkin", resId: id })}>Check in</button>}</>}
      {stay && <><SaveBtn kind="secondary" onClick={() => extend(stay.id, 1)}>Extend 1 night</SaveBtn><button className="btn secondary" onClick={() => open({ t: "move", stayId: stay.id })}>Move room</button><span style={{ flex: 1 }} /><button className="btn primary" onClick={() => open({ t: "checkout", stayId: stay.id })}>Check out</button></>}
      {(res.status === "cancelled" || res.status === "checked_out") && <span className="cap">{res.status === "cancelled" ? `Cancelled: ${res.cancelReason}. The room was released.` : "Stay finished. Kept for records."}</span>}
    </div>
  </>;
}

// ---------- request ----------
function ReqP({ id, close }: { id: string; close: () => void }) {
  const { db, advance, route, toast } = useStore(); const { show } = useRec();
  const q = db.requests.find(x => x.id === id);
  const [r, setR] = useState<WriteResult | null>(null);
  const [to, setTo] = useState<Dept>("Maintenance");
  if (!q) return <Head title="Request" sub="Not found" close={close} />;
  const open = q.status !== "resolved" && q.status !== "cancelled";
  const unrouted = q.dept === "Front desk" && q.status === "received";
  return <>
    <Head title={q.title} sub={<><span className="mono">{q.ref}</span> · Room {q.roomId}{q.guestFirst ? ` · ${q.guestFirst}` : ""}</>} chips={<><ReqChip s={q.status} /><span className="chip s-neutral">{q.dept}</span>{q.priority === "urgent" && <span className="chip s-urgent">Urgent</span>}</>} close={close} />
    <div className="panel-b">
      {q.kind !== "turnover" && <div className="note">“{q.detail}”<div className="cap" style={{ marginTop: 6 }}>via {q.channel}, {hhmm(q.createdAt)}</div></div>}
      <dl className="kv">
        <dt>Time</dt><dd><Sla q={q} /><span className="cap">Target {q.targetMin} min for {q.dept.toLowerCase()}</span></dd>
        <dt>With</dt><dd>{q.assignee || <span className="muted">Nobody yet</span>}</dd>
      </dl>
      {unrouted && <div style={{ padding: "0 16px 16px" }}>
        <div className="alert info"><IconShieldCheck /><div>Roomay wasn't sure which team this is for, so it came to the front desk instead of guessing. Pick the team.</div></div>
        <div style={{ display: "flex", gap: 8, marginTop: 10, alignItems: "center" }}><select className="select" value={to} onChange={e => setTo(e.target.value as Dept)} aria-label="Team"><option>Maintenance</option><option>Housekeeping</option><option>Food & drink</option></select><SaveBtn onClick={async () => setR(await route(id, to, STAFF.reception))}>Send to {to}</SaveBtn></div>
      </div>}
      <div style={{ padding: "0 16px" }}><WriteAlert r={r} what="updated" /></div>
      <div className="sec-h">Timeline</div>
      <div className="log">{[...q.history].reverse().map((h, i) => <div key={i} className="log-i"><time>{when(h.at)}</time><div>{h.text}{h.by && <span className="cap"> · {h.by}</span>}</div></div>)}</div>
      <div style={{ padding: "0 16px 16px" }}><button className="btn ghost sm" style={{ marginLeft: -10 }} onClick={() => show({ t: "room", id: q.roomId })}>Open room {q.roomId}</button></div>
    </div>
    {open && !unrouted && <div className="panel-f">
      <button className="btn secondary" onClick={() => toast({ title: `Reminder sent to ${q.assignee?.split(" ")[0] || q.dept}`, body: `${q.ref}, room ${q.roomId}`, tone: "info" })}>Send reminder</button>
      <span style={{ flex: 1 }} />
      <SaveBtn kind="secondary" onClick={async () => setR(await advance(id, "cancelled", STAFF.reception, "Not needed"))}>Close, not needed</SaveBtn>
      <SaveBtn onClick={async () => setR(await advance(id, "resolved", STAFF.reception))}>Mark resolved</SaveBtn>
    </div>}
  </>;
}
