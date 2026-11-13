import { useEffect, useState } from "react";
import { IconPlus, IconCircleCheck } from "@tabler/icons-react";
import { useStore } from "../store";
import { isOpen, isLate, type Dept } from "../data";
import { Tabs, ReqChip, Sla, Empty } from "../ui";
import { useRec } from "./ctx";

export function Requests() {
  const { db } = useStore(); const { show, panel, open, filter } = useRec();
  const [tab, setTab] = useState<"open" | "late" | "route" | "done">("open");
  const [dept, setDept] = useState<"all" | Dept>((filter as Dept) || "all");
  const [turn, setTurn] = useState(false);
  useEffect(() => { if (filter) setDept(filter as Dept); }, [filter]);
  const base = db.requests.filter(q => (dept === "all" || q.dept === dept) && (turn || q.kind !== "turnover"));
  const pick = { open: (q: typeof base[number]) => isOpen(q), late: isLate, route: (q: typeof base[number]) => q.status === "received" && q.dept === "Front desk", done: (q: typeof base[number]) => !isOpen(q) };
  const list = base.filter(pick[tab]).sort((a, b) => (b.priority === "urgent" ? 1 : 0) - (a.priority === "urgent" ? 1 : 0) || a.createdAt - b.createdAt);
  const sel = panel?.t === "req" ? panel.id : null;
  const ac = [...new Set(db.requests.filter(q => isOpen(q) && /AC/.test(q.title) && q.roomId.startsWith("3")).map(q => q.roomId))].sort();
  return (
    <div className="page">
      <div className="page-h">
        <div className="grow"><h2 className="h-big">Requests</h2><div className="muted" style={{ marginTop: 2 }}>Every guest and staff request, from the first message until it's done.</div></div>
        <button className="btn primary" onClick={() => open({ t: "request" })}><IconPlus />Log request</button>
      </div>
      {ac.length >= 2 && (dept === "all" || dept === "Maintenance") && <div className="alert info" style={{ marginBottom: 12 }}><span className="roomay-tag" style={{ marginTop: 2 }}>ROOMAY</span><div style={{ flex: 1 }}><b>{ac.length} AC problems on floor 3</b> (rooms {ac.join(", ")}). These may share one cause. Ask maintenance to check the floor's AC supply before fixing units one by one.</div><button className="btn secondary sm" onClick={() => show({ t: "req", id: "q-305" })}>Open first report</button></div>}
      <div className="box">
        <Tabs value={tab} onChange={setTab} items={[{ v: "open", label: "Open", n: base.filter(pick.open).length }, { v: "late", label: "Over target", n: base.filter(pick.late).length }, { v: "route", label: "Needs a team", n: base.filter(pick.route).length }, { v: "done", label: "Done today", n: base.filter(pick.done).length }]} />
        <div className="toolbar" style={{ padding: "12px 16px 0", marginBottom: 12 }}>
          <select className="select" value={dept} onChange={e => setDept(e.target.value as "all" | Dept)} aria-label="Team"><option value="all">All teams</option><option>Housekeeping</option><option>Maintenance</option><option>Food & drink</option><option>Front desk</option></select>
          <label style={{ display: "inline-flex", gap: 6, alignItems: "center", fontSize: 13.5, color: "var(--text-2)", cursor: "pointer" }}><input type="checkbox" checked={turn} onChange={e => setTurn(e.target.checked)} />Include departure cleans</label>
        </div>
        {!list.length ? <Empty icon={<IconCircleCheck />} title={tab === "late" ? "Nothing over target" : tab === "route" ? "Nothing waiting for a team" : "No requests here"} body="New guest requests appear here the moment they're sent." />
          : <table className="tbl">
            <thead><tr><th>Room</th><th>Request</th><th>Team</th><th>Status</th><th>Time</th><th className="hide-sm">With</th><th className="hide-sm">From</th></tr></thead>
            <tbody>{list.map(q => <tr key={q.id} className={`click${sel === q.id ? " sel" : ""}`} onClick={() => show({ t: "req", id: q.id })}>
              <td className="roomno">{q.roomId}</td>
              <td className="wrap" style={{ minWidth: 220, maxWidth: 360 }}><div className="cell2"><span style={{ fontWeight: 500 }}>{q.title}{q.priority === "urgent" && <span className="chip s-urgent" style={{ marginLeft: 8 }}>Urgent</span>}</span><small className="ellipsis">{q.kind === "turnover" ? q.detail : `“${q.detail}”`}</small></div></td>
              <td>{q.dept}</td><td><ReqChip s={q.status} /></td><td><Sla q={q} /></td>
              <td className="hide-sm">{q.assignee?.split(" ")[0] || <span className="muted">Nobody</span>}</td><td className="hide-sm">{q.channel}</td>
            </tr>)}</tbody></table>}
      </div>
    </div>
  );
}
