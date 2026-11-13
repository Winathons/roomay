import { useState } from "react";
import { IconSearch, IconEye } from "@tabler/icons-react";
import { useStore } from "../store";
import { day, naira, roomView } from "../data";
import { shortName } from "../ui";
import { useRec } from "./ctx";

export function Guests() {
  const { db } = useStore(); const { show, panel } = useRec();
  const [q, setQ] = useState(""); const [reveal, setReveal] = useState<string | null>(null);
  const stays = db.stays.filter(s => s.status === "in_house").map(s => ({ s, g: db.guests.find(x => x.id === s.guestId)!, res: db.reservations.find(r => r.id === s.resId)! })).filter(x => !q || x.g.name.toLowerCase().includes(q.toLowerCase()) || x.s.roomId.includes(q)).sort((a, b) => a.g.name.split(" ").slice(-1)[0].localeCompare(b.g.name.split(" ").slice(-1)[0]));
  return (
    <div className="page">
      <div className="page-h"><div className="grow"><h2 className="h-big">Guests in house</h2><div className="muted" style={{ marginTop: 2 }}>{stays.length} stays. Contact details stay hidden until you need them, and every view is logged.</div></div>
        <label className="field-search"><IconSearch /><input value={q} onChange={e => setQ(e.target.value)} placeholder="Name or room" aria-label="Search guests" /></label></div>
      <div className="box"><table className="tbl">
        <thead><tr><th>Guest</th><th>Room</th><th>Arrived</th><th>Departs</th><th>Balance</th><th className="hide-sm">Phone</th><th className="hide-sm">Requests</th></tr></thead>
        <tbody>{stays.map(({ s, g, res }) => { const v = roomView(db.rooms.find(r => r.id === s.roomId)!, db); return (
          <tr key={s.id} className={`click${panel?.t === "res" && panel.id === res.id ? " sel" : ""}`} onClick={() => show({ t: "res", id: res.id })}>
            <td><div className="cell2"><span style={{ fontWeight: 500 }}>{shortName(g.name)}</span><small className="mono">{res.ref}</small></div></td>
            <td className="roomno">{s.roomId}</td><td>{day(res.arrivalDay)}</td>
            <td>{s.departDay < 0 ? <span className="chip s-urgent">Overdue</span> : s.departDay === 0 ? <span className="chip s-today">Today</span> : day(s.departDay)}</td>
            <td className="num">{s.amountDue ? <b style={{ fontWeight: 600 }}>{naira(s.amountDue)}</b> : <span className="muted">Settled</span>}</td>
            <td className="hide-sm" onClick={e => e.stopPropagation()}>{reveal === s.id ? <span className="num">{g.phone}</span> : <button className="btn ghost sm" style={{ marginLeft: -10 }} onClick={() => setReveal(s.id)}><IconEye />Show</button>}</td>
            <td className="hide-sm">{v.open.length ? `${v.open.length} open` : <span className="muted">None</span>}</td>
          </tr>); })}</tbody></table></div>
    </div>
  );
}
