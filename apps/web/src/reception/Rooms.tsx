import { useEffect, useMemo, useState } from "react";
import { IconTimeline, IconLayoutGrid, IconSearch, IconPlus, IconUser, IconDoorEnter, IconLock, IconMoodEmpty } from "@tabler/icons-react";
import { useStore, resGuest } from "../store";
import { ROOM_TYPES, roomView, typeOf, day, type Room, type DB } from "../data";
import { Seg, HKChip, BlockChip, OccChip, ReadyChip, shortName, Empty } from "../ui";
import { useRec } from "./ctx";

type F = "all" | "ready" | "dirty" | "occupied" | "arriving" | "blocked";
const DAYS = [-1, 0, 1, 2, 3, 4, 5, 6];

export function Rooms() {
  const { db } = useStore();
  const { filter, panel, show, open } = useRec();
  const [view, setView] = useState<"timeline" | "board">("timeline");
  const [f, setF] = useState<F>((filter as F) || "all");
  const [floor, setFloor] = useState("all"); const [type, setType] = useState("all"); const [q, setQ] = useState("");
  useEffect(() => { if (filter) { setF(filter as F); setView("board"); } }, [filter]);
  const rv = useMemo(() => db.rooms.map(r => ({ r, v: roomView(r, db) })), [db]);
  const match = (x: typeof rv[number], F: F) => F === "all" || (F === "ready" && x.v.ready) || (F === "dirty" && x.r.hk === "dirty" && !x.r.block && !x.v.stay) || (F === "occupied" && !!x.v.stay) || (F === "arriving" && x.v.occ === "arriving") || (F === "blocked" && !!x.r.block);
  const n = (F: F) => rv.filter(x => match(x, F)).length;
  const list = rv.filter(x => match(x, f) && (floor === "all" || String(x.r.floor) === floor) && (type === "all" || x.r.typeId === type) && (!q || x.r.id.includes(q) || (x.v.guest?.name.toLowerCase().includes(q.toLowerCase()) ?? false)));

  return (
    <div className="page">
      <div className="page-h">
        <div className="grow"><h2 className="h-big">Rooms</h2><div className="muted" style={{ marginTop: 2 }}>{db.rooms.length} rooms on 3 floors. Who's in, cleaning and blocks are shown separately.</div></div>
        <label className="field-search"><IconSearch /><input value={q} onChange={e => setQ(e.target.value)} placeholder="Room or guest" aria-label="Find room or guest" /></label>
        <button className="btn secondary" onClick={() => open({ t: "request" })}>Report a problem</button>
        <button className="btn primary" onClick={() => open({ t: "walkin" })}><IconPlus />New walk-in</button>
      </div>
      <div className="toolbar">
        <Seg label="View" value={view} onChange={setView} items={[{ v: "timeline", label: "Timeline", icon: <IconTimeline /> }, { v: "board", label: "Board", icon: <IconLayoutGrid /> }]} />
        <Seg label="Show" value={f} onChange={setF} items={[{ v: "all", label: "All", n: n("all") }, { v: "ready", label: "Ready", n: n("ready") }, { v: "dirty", label: "Dirty, empty", n: n("dirty") }, { v: "occupied", label: "Occupied", n: n("occupied") }, { v: "arriving", label: "Arriving", n: n("arriving") }, { v: "blocked", label: "Blocked", n: n("blocked") }]} />
        <span style={{ flex: 1 }} />
        <select className="select" value={floor} onChange={e => setFloor(e.target.value)} aria-label="Floor"><option value="all">All floors</option><option value="1">Floor 1</option><option value="2">Floor 2</option><option value="3">Floor 3</option></select>
        <select className="select" value={type} onChange={e => setType(e.target.value)} aria-label="Room type"><option value="all">All types</option>{ROOM_TYPES.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
      </div>
      <Legend timeline={view === "timeline"} />
      {!list.length ? <Empty icon={<IconMoodEmpty />} title="No rooms match" body="Nothing fits these filters. Clear them to see every room." action={<button className="btn secondary sm" onClick={() => { setF("all"); setFloor("all"); setType("all"); setQ(""); }}>Clear filters</button>} />
        : view === "timeline" ? <Timeline rooms={list.map(x => x.r)} db={db} sel={panel} show={show} />
        : <Board list={list} db={db} selId={panel?.t === "room" ? panel.id : null} show={show} />}
    </div>
  );
}

function Legend({ timeline }: { timeline: boolean }) {
  return <div className="legend" style={{ margin: "0 0 12px" }}>
    <span className="k" style={{ marginRight: 2 }}>Cleaning</span>
    <span><i style={{ background: "var(--dirty-sw)" }} />Dirty</span><span><i style={{ background: "var(--clean-sw)" }} />Clean</span><span><i style={{ background: "var(--insp-sw)" }} />Inspected</span>
    <span><i style={{ background: "var(--oos-sw)" }} />Out of service</span><span><i style={{ background: "var(--ooo-sw)" }} />Out of order</span>
    {timeline && <><span className="k" style={{ margin: "0 2px 0 10px" }}>Stays</span><span><i style={{ background: "#475467" }} />In house</span><span><i style={{ background: "var(--today)" }} />Arrives or leaves today</span><span><i style={{ background: "var(--urgent-sw)" }} />Overdue</span><span><i style={{ background: "#D9DEE5" }} />Future</span><span><i style={{ outline: "1.5px dashed var(--text-3)", outlineOffset: -1.5 }} />Not confirmed</span></>}
  </div>;
}

function Timeline({ rooms, db, sel, show }: { rooms: Room[]; db: DB; sel: ReturnType<typeof useRec>["panel"]; show: ReturnType<typeof useRec>["show"] }) {
  const cols = DAYS.length; const pct = 100 / cols;
  const pos = (from: number, to: number) => { const a = Math.max(from, DAYS[0]) - DAYS[0], b = Math.min(to, DAYS[cols - 1] + 1) - DAYS[0]; return { left: `calc(${a * pct}% + 2px)`, width: `calc(${(b - a) * pct}% - 4px)` }; };
  const groups = ROOM_TYPES.map(t => ({ t, rooms: rooms.filter(r => r.typeId === t.id).sort((a, b) => a.id.localeCompare(b.id)) })).filter(x => x.rooms.length);
  return (
    <div className="tl" style={{ ["--days" as string]: cols } as React.CSSProperties}>
      <div className="tl-grid tl-head"><div className="tl-corner">Room</div>{DAYS.map(d => <div key={d} className={`tl-day${d === 0 ? " today" : ""}`}><b>{d === 0 ? "Today" : day(d).split(" ")[0]}</b>{day(d).split(" ").slice(1).join(" ")}</div>)}</div>
      {groups.map(({ t, rooms }) => <div key={t.id} className="tl-grid">
        <div className="tl-cat">{t.name} · {rooms.length}</div>
        {rooms.map(r => { const v = roomView(r, db);
          const resList = db.reservations.filter(x => x.roomId === r.id && (x.status === "confirmed" || x.status === "pending") && x.arrivalDay + x.nights > DAYS[0] && x.arrivalDay <= DAYS[cols - 1]);
          const hkCol = r.block ? (r.block.kind === "oos" ? "var(--oos-sw)" : "var(--ooo-sw)") : r.hk === "dirty" ? "var(--dirty-sw)" : r.hk === "clean" ? "var(--clean-sw)" : "var(--insp-sw)";
          return <div key={r.id} style={{ display: "contents" }}>
            <div className="tl-room" onClick={() => show({ t: "room", id: r.id })} role="button" tabIndex={0} aria-label={`Room ${r.id}`} style={sel?.t === "room" && sel.id === r.id ? { background: "var(--selected)" } : undefined}>
              <span className="no">{r.id}</span><span className="hk" style={{ background: hkCol }} aria-hidden /><small>{r.block ? (r.block.kind === "oos" ? "Out of service" : "Out of order") : r.hk === "dirty" ? "Dirty" : r.hk === "clean" ? "Clean" : "Inspected"}</small>
            </div>
            <div className="tl-row">
              {DAYS.map(d => <i key={d} className={d === 0 ? "today" : ""} />)}
              {v.stay && (() => { const res = db.reservations.find(x => x.id === v.stay!.resId); const gg = db.guests.find(x => x.id === v.stay!.guestId)!; const over = v.stay.departDay < 0; const cls = over ? "urgentb" : v.stay.departDay === 0 ? "todayb" : "house";
                return <button className={`bar ${cls}${sel?.t === "res" && sel.id === res?.id ? " sel" : ""}`} style={pos(-1, over ? 0.5 : v.stay.departDay + 0.45)} onClick={() => res && show({ t: "res", id: res.id })} title={`${gg.name} · ${over ? "overdue" : "in house"}`}><IconUser />{shortName(gg.name)}{over && " · overdue"}</button>; })()}
              {resList.map(x => { const gg = resGuest(db, x); const cls = x.status === "pending" ? "pend" : x.arrivalDay === 0 ? "todayb" : "future";
                return <button key={x.id} className={`bar ${cls}${sel?.t === "res" && sel.id === x.id ? " sel" : ""}`} style={pos(x.arrivalDay + 0.55, x.arrivalDay + x.nights + 0.45)} onClick={() => show({ t: "res", id: x.id })} title={`${gg.name} · ${x.status}`}>{x.arrivalDay === 0 && <IconDoorEnter />}{shortName(gg.name)}</button>; })}
              {r.block && <button className={`bar blk${r.block.kind === "ooo" ? " ooo" : ""}`} style={pos(-1, r.block.kind === "ooo" ? 4 : 0.7)} onClick={() => show({ t: "room", id: r.id })}><IconLock />{r.block.reason}</button>}
            </div>
          </div>; })}
      </div>)}
    </div>
  );
}

function Board({ list, db, selId, show }: { list: { r: Room; v: ReturnType<typeof roomView> }[]; db: DB; selId: string | null; show: ReturnType<typeof useRec>["show"] }) {
  return <>{[1, 2, 3].map(fl => { const L = list.filter(x => x.r.floor === fl); if (!L.length) return null; return (
    <section key={fl}><div className="floor-h"><h3 className="h-sec">Floor {fl}</h3><span className="cap">{L.length} rooms, {L.filter(x => x.v.ready).length} ready</span></div>
      <div className="board">{L.map(({ r, v }) => (
        <button key={r.id} className={`tile${selId === r.id ? " sel" : ""}`} onClick={() => show({ t: "room", id: r.id })} aria-label={`Room ${r.id}`}>
          <div className="top"><span className="no">{r.id}</span><span className="cap">{typeOf(r.typeId).short}</span><span style={{ marginLeft: "auto" }}><ReadyChip room={r} db={db} /></span></div>
          <div className="who">{v.guest ? <><IconUser /><span className="ellipsis">{shortName(v.guest.name)}</span></> : <span className="muted">Empty</span>}</div>
          <div className="chips">{v.occ !== "vacant" && <OccChip occ={v.occ} />}{r.block ? <BlockChip room={r} /> : <HKChip hk={r.hk} />}{v.open.length > 0 && <span className="chip s-navy">{v.open.length} request</span>}</div>
        </button>))}</div>
    </section>); })}</>;
}
