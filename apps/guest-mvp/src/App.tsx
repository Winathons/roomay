import { GuestMvp } from "./GuestMvp";
import { PhoneShell } from "./PhoneShell";

// Both direct URLs render the same independent flow. Keep the hash route for the
// Roomay prototype link and make the app root useful for its dedicated preview.
export default function App() {
  return <main className="flows"><div className="guest-preview-heading"><b>Roomay Guest MVP</b><span>Secure guest access · Verification service pending</span></div><PhoneShell label="Roomay guest MVP"><GuestMvp /></PhoneShell></main>;
}
