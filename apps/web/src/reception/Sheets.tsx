import { useMemo, useState } from "react";
import { IconCheck, IconX, IconAlertTriangle, IconInfoCircle, IconCircleCheck } from "@tabler/icons-react";
import { useStore, resGuest, type WriteResult } from "../store";
import { ROOM_TYPES, typeOf, day, naira, roomView, eligibleRooms, triage, STAFF, type Dept } from "../data";
import { Sheet, Opt, Stepper, SaveBtn, WriteAlert, HKChip, BlockChip, ReadyChip, shortName } from "../ui";
import { useRec } from "./ctx";

export function Sheets() {
  const { sheet, open } = useRec(); const close = () => open(null);
  if (!sheet) return null;
  if (sheet.t === "walkin") return <WalkIn close={close} later={!!sheet.later} />;
  if (sheet.t === "edit") return <EditBooking resId={sheet.resId} close={close} />;
  if (sheet.t === "checkin") return <CheckIn key={sheet.resId} resId={sheet.resId} close={close} />;
  if (sheet.t === "checkout") return <CheckOut stayId={sheet.stayId} close={close} />;
  if (sheet.t === "move") return <Move stayId={sheet.stayId} close={close} />;
  if (sheet.t === "cancel") return <Cancel resId={sheet.resId} close={close} />;
  return <LogRequest roomId={sheet.roomId} close={close} />;
}

function Rooms({ list, pick, setPick }: { list: ReturnType<typeof eligibleRooms>; pick?: string; setPick: (s: string) => void }) {
  const [more, setMore] = useState(false);
  return <div style={{ display: "flex", flexDirection: "column", gap: 6 }} role="radiogroup" aria-label="Room">
    {(more ? list.ok : list.ok.slice(0, 4)).map((c, i) => <Opt key={c.room.id} radio on={pick === c.room.id} onClick={() => setPick(c.room.id)}><span style={{ display: "flex", gap: 8, alignItems: "center" }}><b style={{ fontWeight: 600 }}>Room {c.room.id}</b><span className="cap">floor {c.room.floor}</span>{i === 0 && <span className="roomay-tag" style={{ marginLeft: "auto" }}>BEST MATCH</span>}</span><span className="cap">{c.why.join(", ")}</span></Opt>)}
    {list.ok.length > 4 && <button className="btn ghost sm" style={{ alignSelf: "flex-start", marginLeft: -10 }} onClick={() => setMore(v => !v)}>{more ? "Show fewer" : `Show ${list.ok.length - 4} more`}</button>}
    {list.out.length > 0 && <div className="cap" style={{ display: "flex", gap: 6 }}><IconInfoCircle size={14} style={{ flex: "none", marginTop: 1 }} /><span>Not offered: {list.out.slice(0, 3).map(o => `${o.room.id} (${o.why.charAt(0).toLowerCase() + o.why.slice(1)})`).join("; ")}{list.out.length > 3 ? ` and ${list.out.length - 3} more` : ""}.</span></div>}
  </div>;
}

// ---------------- Walk-in: book first (reservation), check in second (stay) ----------------
function WalkIn({ close, later }: { close: () => void; later: boolean }) {
  const { db, createBooking } = useStore(); const { open } = useRec();
  const [step, setStep] = useState(1); const [tried, setTried] = useState(false);
  const [name, setName] = useState(""); const [phone, setPhone] = useState(""); const [adults, setAdults] = useState(1); const [others, setOthers] = useState<string[]>([]);
  const [nights, setNights] = useState(1); const [typeId, setTypeId] = useState("dd"); const [pick, setPick] = useState<string>();
  const [pay, setPay] = useState<"none" | "deposit" | "paid">("none");
  const [arr, setArr] = useState(later ? 1 : 0); const [src, setSrc] = useState<"Phone" | "Email" | "Walk-in">("Phone");
  const [r, setR] = useState<(WriteResult & { resId?: string }) | null>(null);
  const t = typeOf(typeId);
  const list = useMemo(() => eligibleRooms(db, { typeId, arrivalDay: arr, nights, adults }, !later), [db, typeId, nights, adults, arr, later]);
  const room = pick && list.ok.some(c => c.room.id === pick) ? pick : list.ok[0]?.room.id;
  const digits = phone.replace(/\D/g, "");
  const errs = { name: name.trim().split(/\s+/).length < 2 ? "Enter first and last name, as on their ID." : "", phone: !(digits.length === 11 && digits.startsWith("0")) && !(digits.length === 13 && digits.startsWith("234")) ? "Enter a Nigerian mobile number, e.g. 0803 555 0142 or +234 803 555 0142." : "", cap: adults > t.capacity ? `${t.name} sleeps ${t.capacity}. Choose a bigger room type or fewer guests.` : "", others: others.some(o => o.trim().length < 2) ? "Add a name for each extra guest, or remove the row." : "" };
  const next = () => { setTried(true); if (step === 1 && (errs.name || errs.phone || errs.others)) return; if (step === 2 && (errs.cap || !room)) return; setTried(false); setStep(step + 1); };
  const saved = r && (r.ok || r.kind === "duplicate" || r.kind === "unknown");
  const savedRes = r && "resId" in r && r.resId ? db.reservations.find(x => x.id === r.resId) : undefined;

  if (r && r.ok && savedRes) return <Sheet title="Booking saved" sub="Read back from Workpeg" onClose={close}
    footer={later ? <><span style={{ flex: 1 }} /><button className="btn primary" onClick={close}>Done</button></> : <><button className="btn ghost" onClick={close}>Done for now</button><span style={{ flex: 1 }} /><button className="btn primary" onClick={() => open({ t: "checkin", resId: savedRes.id })}>Check in now</button></>}>
    {later ? <div className="alert ok"><IconCircleCheck /><div><b>{savedRes.ref} is saved and confirmed.</b> {savedRes.roomId} is held for {name.split(" ")[0]} from {day(arr)}. Nothing else happens until they arrive. Then check them in from Today.</div></div>
      : <div className="alert ok"><IconCircleCheck /><div><b>{savedRes.ref} is saved and confirmed.</b> {savedRes.roomId} is held for {name.split(" ")[0]}. The guest is <b>not checked in yet</b>. Check them in once you've seen their ID.</div></div>}
    <dl className="summary"><dt>Guest</dt><dd>{name}</dd><dt>Room</dt><dd>{savedRes.roomId}, {t.name}</dd><dt>Dates</dt><dd>{day(arr)} to {day(arr + nights)}</dd>{later && <><dt>Booked by</dt><dd>{src}</dd></>}<dt>Guests</dt><dd>{adults}</dd><dt>Payment</dt><dd>{pay === "paid" ? "Paid in full" : pay === "deposit" ? "Deposit taken" : "Not paid yet"}</dd><dt>Total</dt><dd>{naira(t.rate * nights)}</dd></dl>
  </Sheet>;

  return <Sheet title={later ? "New booking" : "New walk-in"} sub={later ? "For a later date. The room is held as soon as you save." : "Creates a booking. Check-in is the next step."} onClose={close} steps={["Guest", "Room", "Review"]} step={step}
    footer={<>{step > 1 && !saved ? <button className="btn ghost" onClick={() => setStep(step - 1)}>Back</button> : <button className="btn ghost" onClick={close}>Cancel</button>}<span style={{ flex: 1 }} />
      {step < 3 ? <button className="btn primary" onClick={next}>Continue</button> : <SaveBtn disabled={!!saved} onClick={async () => { const x = await createBooking({ name: name.trim(), phone, typeId, roomId: room!, nights, adults, occupants: others.map(o => o.trim()), payment: pay, source: later ? src : "Walk-in", arrivalDay: arr, eta: later ? "14:00" : "Now" }); setR(x); if (!x.ok && x.kind === "conflict") { setPick(undefined); setStep(2); } }}>Create booking</SaveBtn>}</>}>
    {step === 1 && <>
      <div className="f"><label htmlFor="wn">Lead guest's full name</label><input id="wn" className={`in${tried && errs.name ? " bad" : ""}`} value={name} onChange={e => setName(e.target.value)} placeholder="As written on their ID" autoFocus />{tried && errs.name && <span className="err"><IconAlertTriangle size={14} />{errs.name}</span>}</div>
      <div className="f"><label htmlFor="wp">Mobile number</label><input id="wp" className={`in${tried && errs.phone ? " bad" : ""}`} value={phone} onChange={e => setPhone(e.target.value)} placeholder="0803 555 0142" inputMode="tel" />{tried && errs.phone ? <span className="err"><IconAlertTriangle size={14} />{errs.phone}</span> : <span className="help">Used for the My Stay invite. Only staff see it.</span>}</div>
      <div className="f"><span className="lbl">Adults staying</span><Stepper value={adults} set={n => { setAdults(n); setOthers(o => o.slice(0, n - 1)); }} min={1} max={4} label="adults" /></div>
      {adults > 1 && <div className="f"><span className="lbl">Other guests</span><span className="help">Names only. Their IDs are checked at check-in.</span>
        {Array.from({ length: adults - 1 }, (_, i) => <input key={i} className="in" value={others[i] || ""} onChange={e => setOthers(o => { const c = [...o]; c[i] = e.target.value; return c; })} placeholder={`Guest ${i + 2} full name`} />)}
        {tried && errs.others && <span className="err"><IconAlertTriangle size={14} />{errs.others}</span>}</div>}
    </>}
    {step === 2 && <>
      <WriteAlert r={r} what="booked" conflict={`Another receptionist just took the room you picked.`} />
      <div className="row2"><div className="f"><span className="lbl">Nights</span><Stepper value={nights} set={setNights} min={1} max={14} label="nights" /><span className="help">Leaves {day(arr + nights)} at 11:00</span></div>
        {later ? <div className="f"><span className="lbl">Booked by</span><div className="seg" role="radiogroup" aria-label="Booked by">{(["Phone", "Email", "Walk-in"] as const).map(x => <button key={x} className={src === x ? "on" : ""} onClick={() => setSrc(x)}>{x}</button>)}</div></div>
        : <div className="f"><span className="lbl">Arrives</span><div className="in" style={{ display: "flex", alignItems: "center", color: "var(--text-2)" }}>Today, now</div></div>}</div>
      {later && <div className="f"><span className="lbl">Arrives</span><div style={{ display: "flex", gap: 6, flexWrap: "wrap" }} role="radiogroup" aria-label="Arrival date">{[1, 2, 3, 4, 5, 6].map(d => <button key={d} className={`btn sm ${arr === d ? "primary" : "secondary"}`} onClick={() => { setArr(d); setPick(undefined); }}>{day(d)}</button>)}</div><span className="help">Check-in from 14:00. A room is offered only if nothing else is booked or blocked on these dates.</span></div>}
      <div className="f"><span className="lbl">Room type</span><div className="row2" style={{ gap: 8 }}>{ROOM_TYPES.map(rt => { const c = eligibleRooms(db, { typeId: rt.id, arrivalDay: arr, nights, adults }, !later).ok.length; return <Opt key={rt.id} radio on={typeId === rt.id} onClick={() => { setTypeId(rt.id); setPick(undefined); }} disabled={!c}><span style={{ display: "flex", justifyContent: "space-between", gap: 8 }}><b style={{ fontWeight: 600 }}>{rt.name}</b><span className="cap">{c} {later ? "free" : "ready"}</span></span><span className="cap num">{naira(rt.rate)} a night, sleeps {rt.capacity}</span></Opt>; })}</div>
        {tried && errs.cap && <span className="err"><IconAlertTriangle size={14} />{errs.cap}</span>}</div>
      <div className="f"><span className="lbl">Room</span>{list.ok.length ? <Rooms list={list} pick={room} setPick={setPick} /> : <div className="alert warn"><IconAlertTriangle /><div>{later ? <><b>No {t.name} is free on these dates.</b> Choose another type or date.</> : <><b>No {t.name} is ready right now.</b> Choose another type, or ask housekeeping to clean one first.</>}</div></div>}</div>
    </>}
    {step === 3 && <>
      <WriteAlert r={r} what="booked" />
      <dl className="summary"><dt>Guest</dt><dd>{name}</dd><dt>Mobile</dt><dd>{phone}</dd><dt>Guests</dt><dd>{adults}{others.length ? ` (${others.join(", ")})` : ""}</dd><dt>Room</dt><dd>{room}, {t.name}</dd><dt>Dates</dt><dd>{day(arr)} to {day(arr + nights)}</dd>{later && <><dt>Booked by</dt><dd>{src}</dd></>}<dt>Rate</dt><dd>{naira(t.rate)} × {nights}</dd><dt style={{ fontWeight: 600, color: "var(--text)" }}>Total</dt><dd style={{ fontWeight: 600 }}>{naira(t.rate * nights)}</dd></dl>
      <div className="f"><span className="lbl">Payment so far</span><span className="help">Just record what happened at the desk. Roomay never takes or stores card details.</span>
        {([["none", "Not paid yet"], ["deposit", "Deposit taken"], ["paid", "Paid in full"]] as const).map(([v, l]) => <Opt key={v} radio on={pay === v} onClick={() => setPay(v)}>{l}</Opt>)}</div>
    </>}
  </Sheet>;
}

// ---------------- Change dates or room: always re-checked against live bookings and blocks ----------------
function EditBooking({ resId, close }: { resId: string; close: () => void }) {
  const { db, editBooking } = useStore();
  const res = db.reservations.find(x => x.id === resId)!; const g = resGuest(db, res); const t = typeOf(res.typeId);
  const [arr, setArr] = useState(res.arrivalDay); const [nights, setNights] = useState(res.nights); const [pick, setPick] = useState<string | undefined>(res.roomId);
  const [r, setR] = useState<WriteResult | null>(null); const [checked, setChecked] = useState("10:42");
  const list = useMemo(() => eligibleRooms(db, { id: res.id, typeId: res.typeId, arrivalDay: arr, nights, adults: res.adults }, false), [db, res.id, res.typeId, res.adults, arr, nights]);
  const room = pick && list.ok.some(c => c.room.id === pick) ? pick : undefined;
  const lost = !!res.roomId && !list.ok.some(c => c.room.id === res.roomId);
  const changed = arr !== res.arrivalDay || nights !== res.nights || room !== res.roomId;
  if (r && r.ok) return <Sheet title="Booking updated" sub="Read back from Workpeg" onClose={close} footer={<><span style={{ flex: 1 }} /><button className="btn primary" onClick={close}>Done</button></>}>
    <div className="alert ok"><IconCircleCheck /><div><b>{res.ref} now runs {day(arr)} to {day(arr + nights)} in room {room}.</b> The old dates are free again. {g.name.split(" ")[0]} is told by SMS.</div></div></Sheet>;
  return <Sheet title={`Change dates or room · ${res.ref}`} sub={`${g.name} · ${t.name} · ${res.adults} adult${res.adults > 1 ? "s" : ""}`} onClose={close}
    footer={<><button className="btn ghost" onClick={close}>Cancel</button><span style={{ flex: 1 }} /><SaveBtn disabled={!changed || !room} onClick={async () => { const x = await editBooking(res.id, arr, nights, room!); setR(x); if (!x.ok && x.kind === "conflict") { setPick(undefined); setChecked("10:43"); } }}>Save changes</SaveBtn></>}>
    <WriteAlert r={r} what="changed" conflict="Another receptionist just booked that room for these dates." />
    <dl className="summary"><dt>Now</dt><dd>{day(res.arrivalDay)} to {day(res.arrivalDay + res.nights)} · room {res.roomId ?? "not assigned"}</dd><dt>New</dt><dd style={{ fontWeight: 600 }}>{day(arr)} to {day(arr + nights)} · room {room ?? "pick one"}</dd></dl>
    <div className="row2"><div className="f"><span className="lbl">Arrives</span><select className="select" value={arr} onChange={e => setArr(+e.target.value)} aria-label="Arrival date">{[0, 1, 2, 3, 4, 5, 6].map(d => <option key={d} value={d}>{day(d)}</option>)}</select></div>
      <div className="f"><span className="lbl">Nights</span><Stepper value={nights} set={setNights} min={1} max={14} label="nights" /></div></div>
    <div className="f"><span style={{ display: "flex", alignItems: "center", gap: 8 }}><span className="lbl" style={{ flex: 1 }}>Room</span><span className="cap">Availability checked at {checked}</span><button className="btn ghost sm" onClick={() => setChecked("10:43")}>Recheck</button></span>
      {lost && <div className="alert info"><IconInfoCircle /><div>Room {res.roomId} isn't free for the new dates, so pick another. Nothing changes until you save.</div></div>}
      {list.ok.length ? <Rooms list={list} pick={room} setPick={setPick} /> : <div className="alert warn"><IconAlertTriangle /><div><b>No {t.name} is free on these dates.</b> Keep the current dates, or offer another room type.</div></div>}</div>
  </Sheet>;
}

// ---------------- Check-in: separate, staff-authorised transition with explicit criteria ----------------
function CheckIn({ resId, close }: { resId: string; close: () => void }) {
  const { db, checkIn } = useStore();
  const res = db.reservations.find(x => x.id === resId)!; const g = resGuest(db, res); const t = typeOf(res.typeId);
  const booked = res.roomId ? db.rooms.find(r => r.id === res.roomId) : undefined;
  const bookedReady = booked ? roomView(booked, db).ready : false;
  const list = useMemo(() => eligibleRooms(db, res, true), [db, res]);
  const [pick, setPick] = useState<string | undefined>(bookedReady ? booked!.id : list.ok[0]?.room.id);
  const [idDoc, setIdDoc] = useState("NIN slip"); const [idOk, setIdOk] = useState(false); const [othersOk, setOthersOk] = useState(res.adults < 2);
  const [r, setR] = useState<WriteResult | null>(null);
  const room = pick ? db.rooms.find(x => x.id === pick) : undefined; const roomOk = room ? roomView(room, db).ready : false;
  const crit = [
    { ok: res.status === "confirmed", t: "Booking is confirmed", why: "This is still a booking request. Confirm it in Reservations first." },
    { ok: roomOk, t: room ? `Room ${room.id} is ready` : "A ready room is chosen", why: "Pick a room that's empty, cleaned and not blocked." },
    { ok: idOk, t: `${g.name.split(" ")[0]}'s ID checked`, why: "Check the ID against their face and the booking name." },
    { ok: othersOk, t: res.adults > 1 ? `IDs checked for the other ${res.adults - 1} adult${res.adults > 2 ? "s" : ""}` : "No other adults", why: "Hotel policy: every adult shows ID." },
  ];
  const all = crit.every(c => c.ok);
  const done = r?.ok;
  return <Sheet title={`Check in ${g.name}`} sub={<><span className="mono">{res.ref}</span> · {t.name} · {res.nights} night{res.nights > 1 ? "s" : ""} · {res.adults} adult{res.adults > 1 ? "s" : ""}</>} onClose={close}
    footer={done ? <><span style={{ flex: 1 }} /><button className="btn primary" onClick={close}>Done</button></> : <><button className="btn ghost" onClick={close}>Cancel</button><span style={{ flex: 1 }} /><SaveBtn disabled={!all} onClick={async () => setR(await checkIn(resId, pick!))}>Check in to {pick || "…"}</SaveBtn></>}>
    {done ? <div className="alert ok"><IconCircleCheck /><div><b>{g.name} is checked in to {pick}.</b> The stay has started and {g.name.split(" ")[0]} got a My Stay invite code by SMS. Hand over the key card.</div></div> : <>
      <WriteAlert r={r} what="checked in" conflict={`Room ${pick} was just marked Dirty by housekeeping.`} />
      <div className="f"><span className="lbl">Before you check in</span>
        <div className="box divide">{crit.map(c => <div key={c.t} style={{ display: "flex", gap: 10, padding: "10px 12px", alignItems: "flex-start" }}>
          <span style={{ width: 20, height: 20, borderRadius: "50%", display: "grid", placeItems: "center", flex: "none", background: c.ok ? "var(--insp-bg)" : "var(--sunken)", color: c.ok ? "var(--insp)" : "var(--text-4)", boxShadow: c.ok ? "none" : "inset 0 0 0 1px var(--line-2)" }}>{c.ok ? <IconCheck size={13} stroke={3} /> : <IconX size={12} stroke={2.5} />}</span>
          <div><div style={{ fontWeight: 500 }}>{c.t}</div>{!c.ok && <div className="cap">{c.why}</div>}</div></div>)}</div></div>
      <div className="f"><span className="lbl">Room</span>
        {booked && !bookedReady && <div className="alert warn"><IconAlertTriangle /><div><b>Booked room {booked.id} isn't ready.</b> {booked.block ? <BlockChip room={booked} /> : <HKChip hk={booked.hk} />} Choose a ready room. The booking moves with the guest.</div></div>}
        {booked && bookedReady && <div className="hint">Booked room <b className="roomno">{booked.id}</b> <ReadyChip room={booked} db={db} /></div>}
        <Rooms list={list} pick={pick} setPick={setPick} /></div>
      <div className="f"><span className="lbl">Identity</span>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}><select className="select" value={idDoc} onChange={e => setIdDoc(e.target.value)} aria-label="ID document"><option>NIN slip</option><option>International passport</option><option>Driver's licence</option><option>Voter's card</option></select><span className="help">Roomay records that the ID was checked, not the number or a photo.</span></div>
        <Opt on={idOk} onClick={() => setIdOk(v => !v)}><b style={{ fontWeight: 500 }}>I've checked {g.name}'s {idDoc}</b><span className="cap" style={{ display: "block" }}>Name matches the booking and the person in front of me.</span></Opt>
        {res.adults > 1 && <Opt on={othersOk} onClick={() => setOthersOk(v => !v)}><b style={{ fontWeight: 500 }}>I've checked ID for {res.occupants.length ? res.occupants.join(", ") : `the other ${res.adults - 1} adult${res.adults > 2 ? "s" : ""}`}</b></Opt>}
      </div>
      <dl className="summary"><dt>Payment so far</dt><dd>{res.payment === "paid" ? "Paid in full" : res.payment === "deposit" ? "Deposit taken" : "Nothing paid yet"}</dd><dt>Balance at checkout</dt><dd>{res.payment === "paid" ? "₦0" : naira(res.rate * res.nights)}</dd></dl>
    </>}
  </Sheet>;
}

// ---------------- Check-out ----------------
function CheckOut({ stayId, close }: { stayId: string; close: () => void }) {
  const { db, checkOut } = useStore();
  const s = db.stays.find(x => x.id === stayId)!; const g = db.guests.find(x => x.id === s.guestId)!; const res = db.reservations.find(x => x.id === s.resId);
  const reqs = db.requests.filter(q => q.roomId === s.roomId && q.kind === "guest" && q.status !== "resolved" && q.status !== "cancelled");
  const [settled, setSettled] = useState(s.amountDue === 0); const [keys, setKeys] = useState(false);
  const [r, setR] = useState<WriteResult | null>(null);
  if (r?.ok) return <Sheet title="Checked out" sub={`${g.name}, room ${s.roomId}`} onClose={close} footer={<><span style={{ flex: 1 }} /><button className="btn primary" onClick={close}>Done</button></>}>
    <div className="alert ok"><IconCircleCheck /><div><b>{g.name} has checked out.</b> Room {s.roomId} is now <b>Dirty</b> and {STAFF.housekeeping} has a cleaning task. {reqs.length ? `${reqs.length} open request${reqs.length > 1 ? "s were" : " was"} closed.` : ""} The My Stay link no longer works.</div></div></Sheet>;
  return <Sheet title={`Check out ${g.name}`} sub={<>{res && <span className="mono">{res.ref}</span>} · Room {s.roomId}</>} onClose={close}
    footer={<><button className="btn ghost" onClick={close}>Cancel</button><span style={{ flex: 1 }} /><SaveBtn disabled={!settled || !keys} onClick={async () => setR(await checkOut(stayId))}>Check out of {s.roomId}</SaveBtn></>}>
    <WriteAlert r={r} what="checked out" />
    {s.departDay < 0 && <div className="alert warn"><IconAlertTriangle /><div><b>Overdue since yesterday.</b> If the guest is staying on, extend the stay instead.</div></div>}
    <dl className="summary"><dt>Guest</dt><dd>{g.name}</dd><dt>Room</dt><dd>{s.roomId}</dd><dt>Balance due</dt><dd style={{ color: s.amountDue ? "var(--urgent)" : undefined }}>{s.amountDue ? naira(s.amountDue) : "₦0, settled"}</dd></dl>
    {s.amountDue > 0 && <div className="f"><span className="lbl">Balance of {naira(s.amountDue)}</span>
      <Opt on={settled} onClick={() => setSettled(v => !v)}><b style={{ fontWeight: 500 }}>Paid at the desk just now</b><span className="cap" style={{ display: "block" }}>Take payment on the POS as usual. Roomay only records it.</span></Opt>
      <button className="opt" disabled><span className="tick" /><span><b style={{ fontWeight: 500 }}>Bill to company</b><span className="cap" style={{ display: "block" }}>Needs a manager's approval. Ask your manager.</span></span></button></div>}
    <Opt on={keys} onClick={() => setKeys(v => !v)}><b style={{ fontWeight: 500 }}>Key cards returned</b></Opt>
    <div className="alert neutral"><IconInfoCircle /><div>Checking out sets {s.roomId} to <b>Dirty</b>, sends a cleaning task to housekeeping{reqs.length ? <>, and closes {reqs.length} open request{reqs.length > 1 ? "s" : ""}</> : null}.</div></div>
  </Sheet>;
}

// ---------------- Move room (change room) ----------------
function Move({ stayId, close }: { stayId: string; close: () => void }) {
  const { db, changeRoom } = useStore();
  const s = db.stays.find(x => x.id === stayId)!; const g = db.guests.find(x => x.id === s.guestId)!; const res = db.reservations.find(x => x.id === s.resId)!;
  const [typeId, setTypeId] = useState(res.typeId);
  const list = useMemo(() => eligibleRooms(db, { ...res, typeId, arrivalDay: 0, nights: Math.max(1, s.departDay) }, true), [db, res, typeId, s.departDay]);
  const [pick, setPick] = useState<string>(); const room = pick && list.ok.some(c => c.room.id === pick) ? pick : list.ok[0]?.room.id;
  const [why, setWhy] = useState(""); const [note, setNote] = useState(""); const [moving, setMoving] = useState(false);
  const [r, setR] = useState<WriteResult | null>(null);
  const reason = why === "Other" ? note.trim() : why;
  if (r?.ok) return <Sheet title="Guest moved" sub={`${g.name}`} onClose={close} footer={<><span style={{ flex: 1 }} /><button className="btn primary" onClick={close}>Done</button></>}><div className="alert ok"><IconCircleCheck /><div><b>{g.name} is now in {room}.</b> {s.roomId} is set to Dirty for cleaning. Open requests moved with the guest. Remember to issue a new key card.</div></div></Sheet>;
  return <Sheet title={`Move ${g.name}`} sub={`From room ${s.roomId}`} onClose={close}
    footer={<><button className="btn ghost" onClick={close}>Cancel</button><span style={{ flex: 1 }} /><SaveBtn disabled={!room || !reason || !moving} onClick={async () => setR(await changeRoom(stayId, room!, reason))}>Move to {room || "…"}</SaveBtn></>}>
    <WriteAlert r={r} what="moved" conflict={`Room ${room} stopped being ready a moment ago.`} />
    <div className="f"><span className="lbl">Why are they moving?</span><select className="select" value={why} onChange={e => setWhy(e.target.value)} aria-label="Reason"><option value="">Choose a reason</option><option>Maintenance problem in the room</option><option>Guest asked to move</option><option>Upgrade</option><option>Other</option></select>{why === "Other" && <input className="in" value={note} onChange={e => setNote(e.target.value)} placeholder="Short reason, for the record" />}<span className="help">Saved in the stay's history.</span></div>
    <div className="f"><span className="lbl">Room type</span><select className="select" value={typeId} onChange={e => { setTypeId(e.target.value); setPick(undefined); }} aria-label="Room type">{ROOM_TYPES.map(t => <option key={t.id} value={t.id}>{t.name}{t.id === res.typeId ? " (same as booked)" : ""}</option>)}</select></div>
    <div className="f"><span className="lbl">New room</span>{list.ok.length ? <Rooms list={list} pick={room} setPick={setPick} /> : <div className="alert warn"><IconAlertTriangle /><div>No ready room of this type. Try another type.</div></div>}</div>
    <Opt on={moving} onClick={() => setMoving(v => !v)}><b style={{ fontWeight: 500 }}>The guest knows and is moving now</b><span className="cap" style={{ display: "block" }}>Room {s.roomId} is only freed once they've moved, so it isn't given away while their things are still there.</span></Opt>
  </Sheet>;
}

// ---------------- Cancel ----------------
function Cancel({ resId, close }: { resId: string; close: () => void }) {
  const { db, cancel } = useStore();
  const res = db.reservations.find(x => x.id === resId)!; const g = resGuest(db, res);
  const [why, setWhy] = useState(""); const [r, setR] = useState<WriteResult | null>(null);
  const pending = res.status === "pending";
  if (res.status === "checked_in") return <Sheet title="Can't cancel this booking" sub={res.ref} onClose={close} footer={<><span style={{ flex: 1 }} /><button className="btn primary" onClick={close}>OK</button></>}><div className="alert warn"><IconAlertTriangle /><div><b>{g.name} is already checked in.</b> A stay can't be cancelled. Use Check out if they're leaving, or Move room if they're changing rooms.</div></div></Sheet>;
  if (r?.ok) return <Sheet title={pending ? "Request declined" : "Booking cancelled"} sub={res.ref} onClose={close} footer={<><span style={{ flex: 1 }} /><button className="btn primary" onClick={close}>Done</button></>}><div className="alert ok"><IconCircleCheck /><div><b>{res.ref} is {pending ? "declined" : "cancelled"}.</b> {res.roomId ? `Room ${res.roomId} is free again for these dates.` : "No room was held."} {g.name.split(" ")[0]} will be told via {res.source}.</div></div></Sheet>;
  return <Sheet title={pending ? `Decline ${g.name}'s request` : `Cancel ${g.name}'s booking`} sub={<><span className="mono">{res.ref}</span> · {typeOf(res.typeId).name} · {res.arrivalDay === 0 ? "today" : day(res.arrivalDay)}</>} onClose={close}
    footer={<><button className="btn ghost" onClick={close}>Keep it</button><span style={{ flex: 1 }} /><SaveBtn kind="danger" disabled={!why} onClick={async () => setR(await cancel(resId, why))}>{pending ? "Decline request" : "Cancel booking"}</SaveBtn></>}>
    <WriteAlert r={r} what="cancelled" />
    <div className="f"><span className="lbl">Reason</span><select className="select" value={why} onChange={e => setWhy(e.target.value)} aria-label="Reason"><option value="">Choose a reason</option>{pending ? <><option>No rooms of this type</option><option>Dates unavailable</option><option>Couldn't reach guest</option></> : <><option>Guest changed travel plans</option><option>Guest didn't arrive</option><option>Duplicate booking</option></>}</select></div>
    <div className="alert neutral"><IconInfoCircle /><div>{res.roomId ? `Room ${res.roomId} goes back on sale for these dates.` : "No room is held, so nothing else changes."} The reason is saved in the booking history.</div></div>
  </Sheet>;
}

// ---------------- Log request (front desk) ----------------
function LogRequest({ roomId, close }: { roomId?: string; close: () => void }) {
  const { db, createRequest, toast } = useStore();
  const [room, setRoom] = useState(roomId || ""); const [text, setText] = useState(""); const [over, setOver] = useState<Dept | "">("");
  const [r, setR] = useState<WriteResult | null>(null);
  const tr = text.trim().length > 3 ? triage(text) : null; const dept = (over || tr?.dept) as Dept | undefined;
  const valid = db.rooms.some(x => x.id === room) && text.trim().length > 3;
  return <Sheet title="Log a request" sub="For guests who call or come to the desk" onClose={close}
    footer={<><button className="btn ghost" onClick={close}>Cancel</button><span style={{ flex: 1 }} /><SaveBtn disabled={!valid} onClick={async () => { const x = await createRequest({ roomId: room, text: text.trim(), channel: "Front desk", dept }); setR(x); if (x.ok) { toast({ title: `${x.req!.ref} sent to ${x.req!.dept}`, body: `${x.req!.title}, room ${room}`, tone: "ok" }); close(); } }}>Send{dept ? ` to ${dept}` : ""}</SaveBtn></>}>
    <WriteAlert r={r} what="logged" />
    <div className="f"><label htmlFor="lr">Room</label><input id="lr" className="in" style={{ width: 120 }} value={room} onChange={e => setRoom(e.target.value.replace(/\D/g, "").slice(0, 3))} placeholder="204" inputMode="numeric" list="roomlist" /><datalist id="roomlist">{db.rooms.map(x => <option key={x.id} value={x.id} />)}</datalist>{room.length === 3 && !db.rooms.some(x => x.id === room) && <span className="err"><IconAlertTriangle size={14} />There's no room {room}.</span>}</div>
    <div className="f"><label htmlFor="lt">What do they need?</label><textarea id="lt" className="in" rows={3} value={text} onChange={e => setText(e.target.value)} placeholder="In the guest's words, e.g. “The shower has no hot water”" /></div>
    {tr && <div className="box" style={{ padding: 12 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}><span className="roomay-tag">ROOMAY SUGGESTS</span>{tr.priority === "urgent" && <span className="chip s-urgent">Urgent</span>}</div>
      <div style={{ marginTop: 6 }}><b style={{ fontWeight: 600 }}>{tr.title}</b> <span className="ink2">for {tr.dept}, target {tr.targetMin} min.</span></div>
      {tr.sensitive && <div className="alert warn" style={{ marginTop: 8 }}><IconAlertTriangle /><div>{tr.sensitive === "safety" ? "Possible safety issue. Call the duty manager now as well." : tr.sensitive === "payment" ? "Billing questions stay with the front desk. Roomay won't change any charges." : "Never share details about another room's guest."}</div></div>}
      {!tr.confident && <div className="cap" style={{ marginTop: 6 }}>Not sure which team. Pick one below.</div>}
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10 }}><span className="cap">Send to</span><select className="select" value={over || tr.dept} onChange={e => setOver(e.target.value as Dept)} aria-label="Team"><option>Housekeeping</option><option>Maintenance</option><option>Food & drink</option><option>Front desk</option></select></div>
    </div>}
    <div className="cap">{shortName(STAFF.reception)} will be shown as the person who logged it.</div>
  </Sheet>;
}
