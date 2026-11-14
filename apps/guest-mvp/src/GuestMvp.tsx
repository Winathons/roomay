import { useState, type FormEvent } from "react";
import {
  IconAlertTriangle, IconArrowLeft, IconCheck, IconClock,
  IconLock, IconMessageCircle, IconSend, IconShieldCheck,
} from "@tabler/icons-react";
import { triage } from "./triage";

type PreviewRequest = { id: string; ref: string; title: string; detail: string; status: "received" };
type WriteResult = { ok: boolean; kind?: "fail" | "unknown" | "offline"; req?: PreviewRequest };

// WOR-17: frontend-only interaction reference. NEVER use this verifier in a hosted guest flow.
// Stay verification, WorkPeg AI conversation and canonical writes require trusted adapters
// owned by WOR-15 / WOR-69 / WOR-65 / WOR-87.
const DEMO_CODE = "482913";
const DEMO_EXPIRED = "000000";

type Phase = "verify" | "chat" | "review" | "track";
type Bubble = { id: number; who: "guest" | "roomay"; text: string };
type Draft = { text: string; title: string; department: string };
const welcome: Bubble = {
  id: 0, who: "roomay",
  text: "Hello! Ask me about your room, or tell me what you need help with.",
};

function DemoNotice() {
  return <div className="alert warn" style={{ margin: "12px 16px 0", fontSize: 12 }}>
    <IconAlertTriangle size={17} style={{ flexShrink: 0 }} />
    <div><b>Offline UI preview.</b> Stay codes, replies and requests are simulated.
      Nothing reaches WorkPeg AI or hotel staff.</div>
  </div>;
}

export function GuestMvp() {
  const [phase, setPhase] = useState<Phase>("verify");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [tries, setTries] = useState(3);
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<Bubble[]>([welcome]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [request, setRequest] = useState<PreviewRequest | null>(null);
  const [result, setResult] = useState<WriteResult | null>(null);
  const [saving, setSaving] = useState(false);
  const params = new URLSearchParams(window.location.search);
  const stay = params.get("stay") !== "ended"; // Local fixture only; no actual stay record is read.
  const saveOutcome = params.get("preview");
  const data = saveOutcome === "offline" ? "offline" : "synthetic";

  const verify = (e: FormEvent) => {
    e.preventDefault();
    if (tries <= 0) return;
    if (!stay) { setError("This demonstration stay has ended. Ask reception for help."); return; }
    if (code === DEMO_EXPIRED) { setError("This demonstration code has expired. Ask reception for another code."); return; }
    if (code !== DEMO_CODE) {
      const left = tries - 1;
      setTries(left);
      setError(left ? "That code does not match this demonstration stay." : "Too many attempts. Reset the preview to try again.");
      return;
    }
    setError("");
    setPhase("chat");
  };

  const send = (e: FormEvent) => {
    e.preventDefault();
    const value = message.trim().slice(0, 1000);
    if (!value || !stay || draft) return;
    setMessage("");
    const id = Date.now();
    setMessages(m => [...m, { id, who: "guest", text: value }]);
    const lower = value.toLowerCase();
    if (/other (guest|room)|someone else's|another guest|their (code|room)/.test(lower)) {
      setMessages(m => [...m, { id: id + 1, who: "roomay", text: "I can't share another guest's information. Please contact reception." }]);
      return;
    }
    if (/\b(what|where|when|which|how)\b.*\b(wi-?fi|password|hotel polic|check.?out|tv remote)\b|\b(password|hotel polic)\b.*\b(wi-?fi|internet)\b/.test(lower)) {
      setMessages(m => [...m, {
        id: id + 1, who: "roomay",
        text: "This preview has no verified hotel facts connected yet. Reception can help. WorkPeg AI will retrieve authorized room information after integration.",
      }]);
      return;
    }
    const finding = triage(value);
    if (finding.sensitive === "safety") {
      setMessages(m => [...m, { id: id + 1, who: "roomay", text: "If you're in immediate danger, contact reception or emergency services now. This preview has not alerted hotel staff." }]);
      return;
    }
    if (finding.sensitive === "privacy" || finding.sensitive === "payment") {
      setMessages(m => [...m, { id: id + 1, who: "roomay", text: "Please contact reception directly for sensitive guest or billing matters. No request has been sent." }]);
      return;
    }
    setResult(null);
    setDraft({
      text: value,
      title: finding.confident ? finding.title : "Guest needs assistance",
      department: finding.confident ? finding.dept : "Front desk",
    });
    setMessages(m => [...m, { id: id + 1, who: "roomay", text: "I can prepare this for reception. Please review the details before sending." }]);
    setPhase("review");
  };

  const confirm = async () => {
    if (!draft || saving || !stay) return;
    setSaving(true);
    setResult(null);
    try {
      // Explicit preview-only save simulation; this never calls WorkPeg.
      const response: WriteResult = saveOutcome === "fail" || saveOutcome === "unknown" || saveOutcome === "offline"
        ? { ok: false, kind: saveOutcome }
        : { ok: true, req: { id: `preview-${Date.now()}`, ref: `DEMO-${String(Date.now()).slice(-4)}`, title: draft.title, detail: draft.text, status: "received" } };
      setResult(response);
      if (response.ok && response.req) {
        setRequest(response.req);
        setPhase("track");
        setDraft(null);
      }
    } finally { setSaving(false); }
  };

  const restart = () => {
    setPhase("verify"); setCode(""); setError(""); setTries(3);
    setRequest(null); setDraft(null); setResult(null);
    setMessages([welcome]); setMessage("");
  };

  const leaveReview = () => {
    setDraft(null);
    setResult(null);
    setPhase("chat");
  };

  const heading = phase === "verify" ? "Welcome to Roomay"
    : phase === "chat" ? "Ask Roomay"
    : phase === "review" ? "Review your request" : "Request progress";

  return <div className="roomay-guest-mvp" style={{ display: "flex", flexDirection: "column", height: "100%" }}>
    <div className="m-top">
      {phase !== "verify" && <button className="icon-btn" onClick={() => phase === "review" ? leaveReview() : setPhase(phase === "track" ? "chat" : "verify")} aria-label="Back"><IconArrowLeft size={19} /></button>}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="m-title">{heading}</div>
        <div className="cap">{phase === "verify" ? "Verify your stay" : "Room 204 · simulated guest session"}</div>
      </div>
      {phase !== "verify" && <span className="chip s-insp noswatch"><IconShieldCheck size={13} />Demo</span>}
    </div>
    <DemoNotice />
    {phase === "verify" && <form onSubmit={verify} className="m-scroll" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 16, background: "var(--surface)" }}>
      <div><h2 className="h-page">Your room, one conversation.</h2>
        <p className="ink2" style={{ marginTop: 8 }}>Enter the stay code from reception to ask about your room or request help.</p></div>
      <div className="f">
        <label htmlFor="guest-mvp-code">6-digit stay code</label>
        <input id="guest-mvp-code" className="in" value={code} onChange={e => { setCode(e.target.value.replace(/\D/g, "").slice(0, 6)); setError(""); }}
          inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} placeholder="000000" required disabled={tries === 0}
          aria-invalid={!!error} aria-describedby={error ? "guest-mvp-error" : undefined} />
      </div>
      {error && <div id="guest-mvp-error" role="alert" className="alert err"><IconAlertTriangle size={18} /><div>{error}</div></div>}
      <button className="btn primary touch block" disabled={code.length !== 6 || tries === 0}>Verify stay</button>
      <div className="cap"><IconLock size={14} style={{ verticalAlign: -3 }} /> A room number alone must never reveal private stay information.</div>
      <div className="note"><b>Preview only:</b> try code <span className="mono">482913</span>. Real stay-code verification is not connected.</div>
      {tries === 0 && <button type="button" className="btn secondary touch" onClick={restart}>Reset preview</button>}
    </form>}
    {phase === "chat" && <div className="m-scroll" role="log" aria-label="Roomay conversation" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
      {messages.map(m => <div key={m.id} className={`bubble ${m.who === "guest" ? "me" : "them"}`}>{m.text}</div>)}
      {request && <button className="btn secondary touch" onClick={() => setPhase("track")}>View saved preview request · {request.ref}</button>}
      <div className="cap">This preview uses deterministic local replies, not WorkPeg AI.</div>
    </div>}
    {phase === "chat" && <form onSubmit={send} className="composer">
      <textarea rows={1} value={message} maxLength={1000} onChange={e => setMessage(e.target.value)}
        placeholder="Ask about your room or report an issue" aria-label="Message Roomay" />
      <button className="round send" aria-label="Send message" disabled={!message.trim() || !stay}><IconSend /></button>
    </form>}
    {phase === "review" && draft && <div className="m-scroll" style={{ padding: 18, display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="alert info"><IconMessageCircle /><div>Review before sending. Nothing has been submitted yet.</div></div>
      <dl className="summary"><dt>Room</dt><dd>204</dd><dt>Title</dt><dd>{draft.title}</dd>
        <dt>Suggested team</dt><dd>{draft.department} (not assigned)</dd>
        <dt>Details</dt><dd>{draft.text}</dd></dl>
      {result && !result.ok && <div className="alert err" role="alert"><IconAlertTriangle /><div>
        {result.kind === "unknown" ? "The preview could not confirm this request. No local status is available; do not assume hotel staff received it."
          : result.kind === "offline" ? "Offline. Nothing was saved." : "Could not save this preview request."}
      </div></div>}
      <button className="btn primary touch block" onClick={confirm} disabled={saving || data === "offline"}>{saving ? "Checking…" : "Confirm request"}</button>
      <button className="btn secondary touch block" onClick={() => { setMessage(draft.text); setDraft(null); setResult(null); setPhase("chat"); }}>Edit message</button>
    </div>}
    {phase === "track" && <div className="m-scroll" style={{ padding: 18, display: "flex", flexDirection: "column", gap: 15 }}>
      {request ? <>
        <div className="alert ok"><IconCheck /><div><b>Saved in the local preview.</b> No hotel staff have been notified.</div></div>
        <div className="m-card" style={{ padding: 16 }}>
          <div className="cap">Preview reference {request.ref}</div>
          <h2 className="h-sec" style={{ margin: "8px 0" }}>{request.title}</h2>
          <span className="chip s-today">Preview · Received</span>
          <p className="ink2" style={{ marginTop: 10 }}>{request.detail}</p>
        </div>
        <div className="alert neutral"><IconClock /><div>Status is simulated in this browser preview, not WorkPeg Tables. Only committed WorkPeg status can appear after integration.</div></div>
        <button className="btn secondary touch block" onClick={() => setPhase("chat")}>Back to conversation</button>
      </> : <div role="alert" className="alert warn"><IconAlertTriangle /><div>Preview request unavailable. No status can be confirmed.</div></div>}
    </div>}
  </div>;
}
