import { useEffect, useState } from "react";
import { IconLayoutDashboard, IconBath, IconUser, IconArrowsSplit2, IconRefresh, IconBriefcase, IconFileText } from "@tabler/icons-react";
import { StoreProvider, useStore, type Outcome, type DataState } from "./store";
import { Reception } from "./reception/Reception";
import type { Page } from "./reception/ctx";
import { Phone, StaffApp, GuestBooking, GuestStay, GuestChat, WhatsAppStory } from "./mobile";
import { Toasts, ReqChip, Sla } from "./ui";
import { Manager } from "./manager";
import { Docs, DOCS } from "./docs";
import { Kit } from "./kit";
import { hhmm, isOpen } from "./data";

function useRoute() {
  const [h, setH] = useState(window.location.hash || "#/reception/today");
  useEffect(() => { const f = () => setH(window.location.hash || "#/reception/today"); window.addEventListener("hashchange", f); return () => window.removeEventListener("hashchange", f); }, []);
  return h.replace(/^#\//, "").split("/");
}

function Dock({ at }: { at: string }) {
  const { reset, outcome, setOutcome, data, setData } = useStore();
  const L = (href: string, label: string, icon: React.ReactNode, key: string) => <a href={href} className={at === key ? "on" : ""}>{icon}{label}</a>;
  return <nav className="dock" aria-label="Prototype controls">
    {L("#/reception/today", "Front desk", <IconLayoutDashboard />, "reception")}
    {L("#/staff", "Staff phones", <IconBath />, "staff")}
    {L("#/guest", "Guest phones", <IconUser />, "guest")}
    {L("#/live", "Follow-through", <IconArrowsSplit2 />, "live")}
    {L("#/manager/overview", "Manager", <IconBriefcase />, "manager")}
    {L("#/docs", "Handoff", <IconFileText />, "docs")}
    <span className="sep" />
    <label title="What the next save will do">Next save<select value={outcome} onChange={e => setOutcome(e.target.value as Outcome)} aria-label="Next save outcome"><option value="ok">Succeeds</option><option value="conflict">Conflicts</option><option value="fail">Fails</option><option value="unknown">Outcome unknown</option><option value="duplicate">Duplicate</option><option value="denied">Denied (403)</option></select></label>
    <label title="Simulate the data connection">Data<select value={data} onChange={e => setData(e.target.value as DataState)} aria-label="Data state"><option value="synthetic">Loaded</option><option value="loading">Loading</option><option value="empty">No rooms yet</option><option value="offline">Offline</option><option value="401">Signed out</option><option value="403">403 refused</option><option value="400">400 unknown hotel</option><option value="timeout">Timed out</option><option value="partial">Partly loaded</option><option value="stale">Out of date</option></select></label>
    <button onClick={reset} aria-label="Reset prototype data"><IconRefresh />Reset</button>
  </nav>;
}

const Flow = ({ label, sub, children }: { label: string; sub: string; children: React.ReactNode }) => <div className="flow"><div className="flow-l"><b>{label}</b> · {sub}</div>{children}</div>;

function Live() {
  const { db } = useStore();
  const feed = db.requests.filter(q => q.kind === "guest").sort((a, b) => b.history[b.history.length - 1].at - a.history[a.history.length - 1].at).slice(0, 9);
  return <div className="flows">
    <Flow label="Guest" sub="Ada, room 204, My Stay"><Phone label="Guest My Stay"><GuestStay /></Phone></Flow>
    <Flow label="Housekeeping" sub="Halima's phone"><Phone label="Housekeeping app"><StaffApp role="housekeeping" /></Phone></Flow>
    <Flow label="Front desk" sub="Requests, live">
      <div className="box" style={{ width: 420, maxHeight: 844, overflow: "auto" }}>
        <div className="box-h"><h2 className="h-sec grow">Requests</h2><span className="cap">{db.requests.filter(q => q.kind === "guest" && isOpen(q)).length} open</span></div>
        <div className="divide">{feed.map(q => <div key={q.id + q.status} style={{ padding: "12px 16px", display: "grid", gridTemplateColumns: "44px 1fr auto", gap: 10, alignItems: "start" }}>
          <span className="roomno">{q.roomId}</span>
          <div style={{ minWidth: 0 }}><div style={{ fontWeight: 500 }} className="ellipsis">{q.title}</div><div className="cap ellipsis">{q.history[q.history.length - 1].text} · {hhmm(q.history[q.history.length - 1].at)}</div><div style={{ marginTop: 4 }}><Sla q={q} /></div></div>
          <ReqChip s={q.status} /></div>)}</div>
      </div>
    </Flow>
  </div>;
}

function DocIndex() {
  return <div style={{ background: "var(--bg)", minHeight: "100vh", padding: 32 }}><div style={{ width: 760, margin: "0 auto", display: "flex", flexDirection: "column", gap: 12 }}>
    <h1 className="h-big">Design handoff</h1><p className="ink2">Documents for developers and the demo team. Each one is also a frame in Figma.</p>
    <div className="box divide">{DOCS.map(d => <a key={d.id} href={`#/docs/${d.id}`} style={{ display: "flex", gap: 12, padding: "14px 16px", textDecoration: "none", color: "inherit", alignItems: "center" }}><IconFileText size={18} color="var(--text-3)" /><b style={{ fontWeight: 500, flex: 1 }}>{d.title}</b><span className="cap">{d.issue}</span></a>)}</div>
  </div></div>;
}

// one phone on its own: used for the end-to-end walkthrough (#/one/stay/205, #/one/staff/housekeeping)
function OnePhone({ kind, arg }: { kind?: string; arg?: string }) {
  return <div className="flows">{kind === "stay" ? <Flow label="Guest" sub={`Room ${arg || "204"}, My Stay`}><Phone label="My Stay"><GuestStay roomId={arg || "204"} /></Phone></Flow>
    : <Flow label="Staff" sub={arg || "housekeeping"}><Phone label="Staff app"><StaffApp role={(arg as "housekeeping" | "maintenance" | "supervisor") || "housekeeping"} /></Phone></Flow>}</div>;
}

function Routes() {
  const [area, sub, third] = useRoute();
  return <>
    {area === "reception" && <Reception page={(sub as Page) || "today"} />}
    {area === "staff" && <div className="flows">
      <Flow label="Housekeeping" sub="Halima Bello"><Phone label="Housekeeping app"><StaffApp role="housekeeping" /></Phone></Flow>
      <Flow label="Maintenance" sub="Musa Kabiru"><Phone label="Maintenance app"><StaffApp role="maintenance" /></Phone></Flow>
      <Flow label="Supervisor" sub="Grace Etim, inspections"><Phone label="Supervisor app"><StaffApp role="supervisor" /></Phone></Flow>
    </div>}
    {area === "guest" && <div className="flows">
      <Flow label="Book a room" sub="Public, before arrival"><Phone label="Booking request"><GuestBooking /></Phone></Flow>
      <Flow label="Room QR and My Stay" sub="After check-in"><Phone label="My Stay"><GuestStay /></Phone></Flow>
      <Flow label="Ask Roomay" sub="Text and voice"><Phone label="Ask Roomay chat"><GuestChat /></Phone></Flow>
      <Flow label="WhatsApp" sub="Future integration, not live"><Phone label="WhatsApp storyboard"><WhatsAppStory /></Phone></Flow>
    </div>}
    {area === "live" && <Live />}
    {area === "one" && <OnePhone kind={sub} arg={third} />}
    {area === "manager" && <Manager page={(sub as "overview" | "team" | "setup") || "overview"} />}
    {area === "kit" && <Kit />}
    {area === "docs" && (sub ? <Docs id={sub} /> : <DocIndex />)}
    <Toasts /><Dock at={area} />
  </>;
}
export default function App() { return <StoreProvider><Routes /></StoreProvider>; }
