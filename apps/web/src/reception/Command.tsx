import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { IconSearch, IconDoorEnter, IconMessageCircle, IconBed, IconUser, IconLayoutDashboard, IconCalendarEvent, IconUsers, IconRefresh, IconFileText } from "@tabler/icons-react";
import { useStore } from "../store";
import { typeOf, roomView } from "../data";
import { useRec } from "./ctx";

interface Item { id: string; g: string; label: string; hint?: string; icon: ReactNode; run: () => void }
export function CommandMenu({ onClose }: { onClose: () => void }) {
  const { db, reset } = useStore(); const { go, open, show } = useRec();
  const [q, setQ] = useState(""); const [i, setI] = useState(0); const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  const items = useMemo<Item[]>(() => {
    const all: Item[] = [
      { id: "walk", g: "Actions", label: "New walk-in", hint: "N", icon: <IconDoorEnter />, run: () => open({ t: "walkin" }) },
      { id: "book", g: "Actions", label: "New booking for a later date", icon: <IconDoorEnter />, run: () => open({ t: "walkin", later: true }) },
      { id: "req", g: "Actions", label: "Log a request", icon: <IconMessageCircle />, run: () => open({ t: "request" }) },
      ...([["today", "Today", <IconLayoutDashboard />], ["rooms", "Rooms", <IconBed />], ["reservations", "Reservations", <IconCalendarEvent />], ["requests", "Requests", <IconMessageCircle />], ["guests", "Guests", <IconUsers />]] as const).map(([p, l, ic]) => ({ id: "go-" + p, g: "Go to", label: l, icon: ic, run: () => go(p) })),
      ...db.stays.filter(s => s.status === "in_house").map(s => { const g = db.guests.find(x => x.id === s.guestId)!; return { id: "s" + s.id, g: "Guests", label: g.name, hint: `Room ${s.roomId}`, icon: <IconUser />, run: () => { go("guests"); setTimeout(() => show({ t: "res", id: s.resId }), 0); } }; }),
      ...db.reservations.map(r => ({ id: "r" + r.id, g: "Bookings", label: r.ref, hint: db.guests.find(x => x.id === r.guestId)!.name, icon: <IconFileText />, run: () => { go("reservations"); setTimeout(() => show({ t: "res", id: r.id }), 0); } })),
      ...db.rooms.map(r => { const v = roomView(r, db); return { id: "rm" + r.id, g: "Rooms", label: `Room ${r.id}`, hint: `${typeOf(r.typeId).name}${v.guest ? ", " + v.guest.name : ""}`, icon: <IconBed />, run: () => { go("rooms"); setTimeout(() => show({ t: "room", id: r.id }), 0); } }; }),
      { id: "reset", g: "Prototype", label: "Reset prototype data", icon: <IconRefresh />, run: reset },
    ];
    const t = q.trim().toLowerCase();
    if (!t) return all.filter(x => x.g === "Actions" || x.g === "Go to");
    return all.filter(x => (x.label + " " + (x.hint || "")).toLowerCase().includes(t)).slice(0, 12);
  }, [q, db, go, open, show, reset]);
  useEffect(() => setI(0), [q]);
  const run = (it?: Item) => { if (!it) return; onClose(); it.run(); };
  let last = "";
  return <>
    <div className="scrim" style={{ zIndex: 50 }} onClick={onClose} />
    <div className="cmd" role="dialog" aria-label="Search">
      <div className="cmd-in"><IconSearch /><input ref={ref} value={q} onChange={e => setQ(e.target.value)} placeholder="Guest, room number, RMY reference or action" aria-label="Search"
        onKeyDown={e => { if (e.key === "ArrowDown") { e.preventDefault(); setI(x => Math.min(items.length - 1, x + 1)); } else if (e.key === "ArrowUp") { e.preventDefault(); setI(x => Math.max(0, x - 1)); } else if (e.key === "Enter") run(items[i]); else if (e.key === "Escape") onClose(); }} /><span className="kbd">Esc</span></div>
      <div className="cmd-list" role="listbox">
        {!items.length && <div className="muted" style={{ padding: 20, textAlign: "center" }}>Nothing matches “{q}”. Try a surname or a room number.</div>}
        {items.map((it, idx) => { const h = it.g !== last ? <div className="cmd-g">{it.g}</div> : null; last = it.g;
          return <div key={it.id}>{h}<button role="option" aria-selected={idx === i} className={`cmd-i${idx === i ? " on" : ""}`} onMouseMove={() => setI(idx)} onClick={() => run(it)}>{it.icon}<span style={{ flex: 1, fontWeight: 500 }}>{it.label}</span>{it.hint && <span className="cap">{it.hint}</span>}</button></div>; })}
      </div>
    </div>
  </>;
}
