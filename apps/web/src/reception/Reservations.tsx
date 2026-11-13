import { useState } from "react";
import { IconSearch, IconPlus, IconCalendarOff } from "@tabler/icons-react";
import { useStore, resGuest } from "../store";
import { ROOM_TYPES, typeOf, day, naira, type ResStatus } from "../data";
import { Tabs, ResChip, shortName, Empty } from "../ui";
import { useRec } from "./ctx";

export function Reservations() {
  const { db } = useStore(); const { show, panel, open } = useRec();
  const [tab, setTab] = useState<"all" | ResStatus>("pending");
  const [src, setSrc] = useState("all"); const [when, setWhen] = useState("all"); const [type, setType] = useState("all"); const [unassigned, setUnassigned] = useState(false); const [q, setQ] = useState("");
  const base = db.reservations.filter(r => (src === "all" || r.source === src) && (type === "all" || r.typeId === type) && (when === "all" || (when === "today" ? r.arrivalDay === 0 : r.arrivalDay >= 0 && r.arrivalDay <= 7)) && (!unassigned || !r.roomId) && (!q || resGuest(db, r).name.toLowerCase().includes(q.toLowerCase()) || r.ref.toLowerCase().includes(q.toLowerCase())));
  const n = (s: "all" | ResStatus) => base.filter(r => s === "all" || r.status === s).length;
  const list = base.filter(r => tab === "all" || r.status === tab).sort((a, b) => a.arrivalDay - b.arrivalDay || a.eta.localeCompare(b.eta));
  const sel = panel?.t === "res" ? panel.id : null;
  return (
    <div className="page">
      <div className="page-h">
        <div className="grow"><h2 className="h-big">Reservations</h2><div className="muted" style={{ marginTop: 2 }}>A request isn't a booking until you confirm it against live rooms. A booking isn't a stay until the guest checks in.</div></div>
        <button className="btn secondary" onClick={() => open({ t: "walkin" })}>New walk-in</button><button className="btn primary" onClick={() => open({ t: "walkin", later: true })}><IconPlus />New booking</button>
      </div>
      <div className="box">
        <Tabs value={tab} onChange={setTab} items={[{ v: "pending", label: "Pending confirmation", n: n("pending") }, { v: "confirmed", label: "Confirmed", n: n("confirmed") }, { v: "checked_in", label: "Checked in", n: n("checked_in") }, { v: "cancelled", label: "Cancelled", n: n("cancelled") }, { v: "all", label: "All", n: n("all") }]} />
        <div className="toolbar" style={{ padding: "12px 16px 0", marginBottom: 12 }}>
          <label className="field-search"><IconSearch /><input value={q} onChange={e => setQ(e.target.value)} placeholder="Guest or RMY reference" aria-label="Search reservations" /></label>
          <select className="select" value={when} onChange={e => setWhen(e.target.value)} aria-label="Arrival"><option value="all">Any arrival</option><option value="today">Arriving today</option><option value="week">Next 7 days</option></select>
          <select className="select" value={src} onChange={e => setSrc(e.target.value)} aria-label="Source"><option value="all">Any source</option><option>Web</option><option>WhatsApp</option><option>Phone</option><option>Walk-in</option></select>
          <select className="select" value={type} onChange={e => setType(e.target.value)} aria-label="Room type"><option value="all">Any room type</option>{ROOM_TYPES.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
          <label style={{ display: "inline-flex", gap: 6, alignItems: "center", fontSize: 13.5, color: "var(--text-2)", cursor: "pointer" }}><input type="checkbox" checked={unassigned} onChange={e => setUnassigned(e.target.checked)} />No room assigned</label>
        </div>
        {!list.length ? <Empty icon={<IconCalendarOff />} title={tab === "pending" ? "No requests waiting" : "Nothing matches"} body={tab === "pending" ? "New web and WhatsApp booking requests appear here for you to confirm." : "Try another status or clear the filters."} />
          : <table className="tbl">
            <thead><tr><th>Reference</th><th>Guest</th><th>Arrives</th><th>Nights</th><th>Room</th><th className="hide-sm">Source</th><th>Status</th><th className="r hide-sm">Total</th></tr></thead>
            <tbody>{list.map(r => <tr key={r.id} className={`click${sel === r.id ? " sel" : ""}`} onClick={() => show({ t: "res", id: r.id })}>
              <td className="mono">{r.ref}</td>
              <td><div className="cell2"><span style={{ fontWeight: 500 }}>{shortName(resGuest(db, r).name)}</span><small>{r.adults} guest{r.adults > 1 ? "s" : ""}</small></div></td>
              <td><div className="cell2"><span className="num">{r.arrivalDay === 0 ? "Today" : day(r.arrivalDay)}</span><small className="num">{r.status === "checked_in" ? "Arrived" : r.eta}</small></div></td>
              <td className="num">{r.nights}</td>
              <td><div className="cell2"><span className="roomno">{r.roomId || <span className="muted" style={{ fontWeight: 400 }}>Not assigned</span>}</span><small>{typeOf(r.typeId).name}</small></div></td>
              <td className="hide-sm">{r.source}</td>
              <td><ResChip s={r.status} /></td>
              <td className="r num hide-sm">{naira(r.rate * r.nights)}</td>
            </tr>)}</tbody></table>}
      </div>
    </div>
  );
}
