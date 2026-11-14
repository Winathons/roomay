import { useEffect, useState, type ReactNode } from "react";
import { IconWifi } from "@tabler/icons-react";

export function PhoneShell({ children, label }: { children: ReactNode; label: string }) {
  const [time, setTime] = useState(() => new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" }));
  useEffect(() => {
    const timer = window.setInterval(() => setTime(new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })), 10_000);
    return () => window.clearInterval(timer);
  }, []);
  return <div className="phone" role="region" aria-label={label}><div className="screen"><div className="island" /><div className="statusbar"><span className="num">{time}</span><span className="sys"><IconWifi size={16} stroke={2.2} /><svg width="25" height="12" viewBox="0 0 25 12" aria-hidden="true"><rect x=".5" y=".5" width="21" height="11" rx="3" fill="none" stroke="currentColor" opacity=".5" /><rect x="2" y="2" width="15" height="8" rx="1.5" fill="currentColor" /><rect x="22.5" y="4" width="2" height="4" rx="1" fill="currentColor" opacity=".5" /></svg></span></div>{children}<div className="home-ind" /></div></div>;
}
