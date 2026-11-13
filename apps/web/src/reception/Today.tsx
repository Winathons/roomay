import { useMemo, useState } from "react";
import { IconPlus, IconMessageCircle, IconX, IconInfoCircle } from "@tabler/icons-react";
import { useStore, resGuest } from "../store";
import { STAFF, day, naira, roomView, typeOf, eligibleRooms, isOpen, isLate, type Reservation, type Stay } from "../data";
import { Tabs, ReadyChip, HKChip, BlockChip, ResChip, Sla, shortName, SaveBtn, ReqChip } from "../ui";
import { useRec } from "./ctx";

export function Today() {
  const { db, extend } = useStore();
  const { go, open, show, panel } = useRec();
  const [tab, setTab] = useState<"arr" | "dep" | "in">("arr");
  const [hints, setHints] = useState(() => { try { return !localStorage.getItem("roomay-hints"); } catch { return true; } });

  const rv = useMemo(() => db.rooms.map(r => ({ r, v: roomView(r, db) })), [db]);
  const stays = db.stays.filter(s => s.status === "in_house");
  const arrivals = db.reservations.filter(r => r.arrivalDay === 0 && (r.status === "confirmed" || r.status === "pending")).sort((a, b) => a.eta.localeCompare(b.eta));
  const departures = stays.filter(s => s.departDay <= 0).sort((a, b) => a.departDay - b.departDay);
  const overdue = stays.filter(s => s.departDay < 0);
  const ready = rv.filter(x => x.v.ready);
  const notReady = rv.filter(x => !x.r.block && !x.v.stay && x.r.hk === "dirty");
  const blocked = rv.filter(x => x.r.block);
  const openReq = db.requests.filter(q => q.kind !== "turnover" && isOpen(q));
  const late = openReq.filter(isLate);
  const atRisk = arrivals.filter(a => a.status === "confirmed" && a.roomId && !roomView(db.rooms.find(r => r.id === a.roomId)!, db).ready);
  const routing = openReq.filter(q => q.status === "received" && q.dept === "Front desk");
  const escalated = db.requests.filter(q => q.status === "escalated");
  const pending = db.reservations.filter(r => r.status === "pending");
  const acRooms = [...new Set([...db.requests.filter(q => isOpen(q) && /AC/.test(q.title)).map(q => q.roomId), ...db.rooms.filter(r => r.block && /AC/.test(r.block.reason)).map(r => r.id)])].filter(id => id.startsWith("3")).sort();
  const sel = panel?.t === "res" ? panel.id : null;
  const g = (s: Stay) => db.guests.find(x => x.id === s.guestId)!;
  const dismissHints = () => { setHints(false); try { localStorage.setItem("roomay-hints", "1"); } catch { /* storage unavailable */ } };

  const K = (l: string, v: React.ReactNode, m: React.ReactNode, onClick: () => void, warn?: boolean) => <button className="kpi" onClick={onClick}><span className="l">{l}</span><span className="v">{v}</span><span className={`m${warn ? " warn" : ""}`}>{m}</span></button>;

  return (
    <div className="page">
      <div className="page-h">
        <div className="grow"><div className="h-big">{day(0, "long")}</div><div className="muted" style={{ marginTop: 2 }}>Check-out by {"11:00"}. Check-in from {"14:00"}. On shift: {STAFF.reception}, {STAFF.reception2}.</div></div>
        <button className="btn secondary" onClick={() => open({ t: "request" })}><IconMessageCircle />Log request</button>
        <button className="btn primary" onClick={() => open({ t: "walkin" })}><IconPlus />New walk-in<span className="kbd" style={{ background: "transparent", color: "#C9D3E0", boxShadow: "inset 0 0 0 1px rgba(255,255,255,.3)" }}>N</span></button>
      </div>

      {hints && <div className="alert info" style={{ marginBottom: 16 }}><IconInfoCircle /><div style={{ flex: 1 }}><b>New to Roomay?</b> Each room shows three separate things: who's in it, whether it's cleaned (<b>Dirty</b>, <b>Clean</b>, <b>Inspected</b>), and whether it's blocked. A room is <b>Ready</b> only when it's empty, cleaned and not blocked. <span className="kbd-hint">Press <span className="kbd">N</span> for a walk-in or <span className="kbd">/</span> to find anything.</span></div><button className="icon-btn" aria-label="Dismiss help" onClick={dismissHints}><IconX /></button></div>}

      <section className="kpis" aria-label="Today in numbers">
        {K("In house", <>{stays.length}<small> / {db.rooms.length}</small></>, `${Math.round(stays.length / db.rooms.length * 100)}% occupied`, () => go("guests"))}
        {K("Arrivals", arrivals.length, atRisk.length ? `${atRisk.length} room not ready` : "All rooms ready", () => { setTab("arr"); }, atRisk.length > 0)}
        {K("Departures", departures.length, `Due by 11:00`, () => setTab("dep"))}
        {K("Overdue", overdue.length, overdue.length ? "Past check-out time" : "None", () => setTab("dep"), overdue.length > 0)}
        {K("Ready", ready.length, "Empty and cleaned", () => go("rooms", "ready"))}
        {K("Not ready", notReady.length, "Empty but dirty", () => go("rooms", "dirty"))}
        {K("Blocked", blocked.length, "Not for sale", () => go("rooms", "blocked"))}
        {K("Open requests", openReq.length, late.length ? `${late.length} over target` : "All within target", () => go("requests"), late.length > 0)}
      </section>

      <div className="today-grid">
        <section className="box" aria-label="Arrivals and departures">
          <Tabs value={tab} onChange={setTab} items={[{ v: "arr", label: "Arrivals", n: arrivals.length }, { v: "dep", label: "Departures", n: departures.length }, { v: "in", label: "In house", n: stays.length }]} />
          {tab === "arr" && <table className="tbl">
            <thead><tr><th>Guest</th><th>Room</th><th>ETA</th><th>Room status</th><th className="hide-sm">Booking</th><th className="r"></th></tr></thead>
            <tbody>{arrivals.map(a => <ArrivalRow key={a.id} a={a} sel={sel === a.id} />)}</tbody></table>}
          {tab === "dep" && <table className="tbl">
            <thead><tr><th>Guest</th><th>Room</th><th>Due</th><th>Balance</th><th>Requests</th><th className="r"></th></tr></thead>
            <tbody>{departures.map(s => { const res = db.reservations.find(r => r.id === s.resId)!; const v = roomView(db.rooms.find(r => r.id === s.roomId)!, db); return (
              <tr key={s.id} className={`click${sel === s.resId ? " sel" : ""}`} onClick={() => show({ t: "res", id: s.resId })}>
                <td><div className="cell2"><span style={{ fontWeight: 500 }}>{shortName(g(s).name)}</span><small className="mono">{res.ref}</small></div></td>
                <td><div className="cell2"><span className="roomno">{s.roomId}</span><small>{typeOf(res.typeId).name}</small></div></td>
                <td>{s.departDay < 0 ? <span className="chip s-urgent">Overdue since yesterday</span> : <span className="num">Today 11:00</span>}</td>
                <td className="num">{s.amountDue ? <span style={{ fontWeight: 600 }}>{naira(s.amountDue)}</span> : <span className="muted">Settled</span>}</td>
                <td>{v.open.length ? <span className="chip s-today">{v.open.length} open</span> : <span className="muted">None</span>}</td>
                <td className="r" onClick={e => e.stopPropagation()}><div style={{ display: "inline-flex", gap: 6 }}>{s.departDay < 0 && <SaveBtn kind="secondary" size="sm" onClick={() => extend(s.id, 1)}>Extend 1 night</SaveBtn>}<button className="btn primary sm" onClick={() => open({ t: "checkout", stayId: s.id })}>Check out</button></div></td>
              </tr>); })}</tbody></table>}
          {tab === "in" && <table className="tbl">
            <thead><tr><th>Guest</th><th>Room</th><th>Departs</th><th>Balance</th><th className="r"></th></tr></thead>
            <tbody>{stays.slice().sort((a, b) => a.roomId.localeCompare(b.roomId)).map(s => { const res = db.reservations.find(r => r.id === s.resId)!; return (
              <tr key={s.id} className={`click${sel === s.resId ? " sel" : ""}`} onClick={() => show({ t: "res", id: s.resId })}>
                <td><div className="cell2"><span style={{ fontWeight: 500 }}>{shortName(g(s).name)}</span><small className="mono">{res.ref}</small></div></td>
                <td className="roomno">{s.roomId}</td>
                <td>{s.departDay < 0 ? <span className="chip s-urgent">Overdue</span> : s.departDay === 0 ? <span className="chip s-today">Today</span> : day(s.departDay)}</td>
                <td className="num">{s.amountDue ? naira(s.amountDue) : <span className="muted">Settled</span>}</td>
                <td className="r"><button className="btn ghost sm" onClick={e => { e.stopPropagation(); open({ t: "move", stayId: s.id }); }}>Move room</button></td>
              </tr>); })}</tbody></table>}
        </section>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <section className="box" aria-label="Needs attention">
            <div className="box-h"><h2 className="h-sec grow">Needs attention</h2><span className="cap">Most urgent first</span></div>
            <div className="divide">
              {overdue.map(s => <Item key={s.id} chip={<span className="chip s-urgent">Overdue</span>} title={`${g(s).name}, room ${s.roomId}`} sub="Was due out yesterday at 11:00. Extend the stay or check out." action={<button className="btn secondary sm" onClick={() => show({ t: "res", id: s.resId })}>Open</button>} />)}
              {escalated.map(q => <Item key={q.id} chip={<ReqChip s="escalated" />} title={`${q.title}, room ${q.roomId}`} sub={q.history[q.history.length - 1].text} action={<button className="btn secondary sm" onClick={() => show({ t: "req", id: q.id })}>Open</button>} />)}
              {late.map(q => <Item key={q.id} chip={<span className="chip s-urgent">Over target</span>} title={`${q.title}, room ${q.roomId}`} sub={<><Sla q={q} compact /> · {q.assignee ? `with ${q.assignee.split(" ")[0]}` : "not picked up"}</>} action={<button className="btn secondary sm" onClick={() => show({ t: "req", id: q.id })}>Open</button>} />)}
              {routing.map(q => <Item key={q.id} chip={<span className="chip s-neutral">Needs a team</span>} title={`${q.title}, room ${q.roomId}`} sub={`"${q.detail}"`} action={<button className="btn secondary sm" onClick={() => show({ t: "req", id: q.id })}>Route</button>} />)}
              {pending.map(r => <Item key={r.id} chip={<span className="chip dash">Pending</span>} title={`Booking request, ${resGuest(db, r).name}`} sub={`${typeOf(r.typeId).name}, ${r.arrivalDay === 0 ? "tonight" : day(r.arrivalDay)}, ${r.nights} nights, via ${r.source}`} action={<button className="btn secondary sm" onClick={() => { go("reservations"); setTimeout(() => show({ t: "res", id: r.id }), 0); }}>Review</button>} />)}
              {acRooms.length >= 2 && <Item chip={<span className="roomay-tag">ROOMAY</span>} title={`${acRooms.length} AC problems on floor 3 since yesterday`} sub={`Rooms ${acRooms.join(", ")}. Could be one shared fault. Worth one check of the floor's AC before fixing each unit.`} action={<button className="btn secondary sm" onClick={() => go("requests", "Maintenance")}>View</button>} />}
            </div>
          </section>

          <section className="box" aria-label="Housekeeping">
            <div className="box-h"><h2 className="h-sec grow">Housekeeping</h2><button className="btn ghost sm" onClick={() => go("rooms", "dirty")}>Open board</button></div>
            <div style={{ padding: "12px 16px", display: "grid", gridTemplateColumns: "1fr auto", rowGap: 8, fontSize: 13.5 }}>
              {([["dirty", "Dirty, empty", notReady.length], ["clean", "Clean, not inspected", rv.filter(x => !x.r.block && !x.v.stay && x.r.hk === "clean").length], ["insp", "Inspected", rv.filter(x => !x.r.block && !x.v.stay && x.r.hk === "inspected").length], ["oos", "Out of service", blocked.filter(x => x.r.block!.kind === "oos").length], ["ooo", "Out of order", blocked.filter(x => x.r.block!.kind === "ooo").length]] as const).map(([k, l, n]) => <div key={k} style={{ display: "contents" }}><span className={`chip plain s-${k}`}>{l}</span><span className="num" style={{ fontWeight: 600 }}>{n}</span></div>)}
            </div>
            <div className="cap" style={{ padding: "0 16px 12px" }}>{db.requests.filter(q => q.kind === "turnover" && isOpen(q)).length} departure cleans open, all with {STAFF.housekeeping}.</div>
          </section>
        </div>
      </div>
    </div>
  );

}

function ArrivalRow({ a, sel }: { a: Reservation; sel: boolean }) {
  const { db } = useStore();
  const { open, show, go } = useRec();
    const room = a.roomId ? db.rooms.find(r => r.id === a.roomId) : undefined;
    const v = room ? roomView(room, db) : undefined;
    const alt = room && v && !v.ready && a.status === "confirmed" ? eligibleRooms(db, a, true).ok.find(c => c.room.id !== room.id && c.why.every(w => !w.startsWith("Open issue"))) : undefined;
    const { reassignTo } = useReassign();
    return (
      <tr className={`click${sel ? " sel" : ""}`} onClick={() => show({ t: "res", id: a.id })}>
        <td style={{ whiteSpace: "nowrap" }}><div className="cell2"><span style={{ fontWeight: 500 }}>{shortName(resGuest(db, a).name)}</span><small>{a.adults} adult{a.adults > 1 ? "s" : ""}, {a.nights} night{a.nights > 1 ? "s" : ""}</small></div></td>
        <td>{room ? <div className="cell2"><span className="roomno">{room.id}</span><small>{typeOf(a.typeId).short}</small></div> : <div className="cell2" style={{ whiteSpace: "nowrap" }}><span className="muted">None yet</span><small>{typeOf(a.typeId).short}</small></div>}</td>
        <td className="num">{a.eta}</td>
        <td>{room && v ? <div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>{v.ready ? <ReadyChip room={room} db={db} /> : <>{room.block ? <BlockChip room={room} /> : <HKChip hk={room.hk} />}</>}</div>
          {alt && <div className="suggest" onClick={e => e.stopPropagation()} title={`Roomay: ${alt.room.id} is ${alt.room.hk} and free`}><span className="roomay-tag">ROOMAY</span><SaveBtn kind="ghost" size="sm" className="link" onClick={() => reassignTo(a.id, alt.room.id)}>Move to {alt.room.id}</SaveBtn><span className="cap">{alt.room.hk === "inspected" ? "inspected" : "clean"}</span></div>}
        </div> : <span className="cap">Assign at confirmation</span>}</td>
        <td className="hide-sm">{a.status === "pending" ? <span className="chip dash">Pending</span> : <ResChip s={a.status} />}</td>
        <td className="r" onClick={e => e.stopPropagation()}>{a.status === "pending" ? <button className="btn secondary sm" onClick={() => { go("reservations"); setTimeout(() => show({ t: "res", id: a.id }), 0); }}>Review</button> : <button className={`btn sm ${v?.ready ? "primary" : "secondary"}`} onClick={() => open({ t: "checkin", resId: a.id })}>Check in</button>}</td>
      </tr>
    );
  }

function Item({ chip, title, sub, action }: { chip: React.ReactNode; title: string; sub: React.ReactNode; action: React.ReactNode }) {
  return <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 4, padding: "12px 16px", alignItems: "start" }}>
    <div style={{ minWidth: 0 }}><div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>{chip}<span style={{ fontWeight: 500 }}>{title}</span></div><div className="cap" style={{ marginTop: 4, fontSize: 12.5, color: "var(--text-2)" }}>{sub}</div></div>
    <div>{action}</div>
  </div>;
}

function useReassign() {
  const { confirm, toast } = useStore();
  return { reassignTo: async (resId: string, roomId: string) => { const r = await confirm(resId, roomId); if (!r.ok) toast({ title: "Couldn't move the booking", body: "Open it to see why. Nothing was changed.", tone: "warn" }); } };
}
