import { GuestHome } from "@/features/home/guest-home";
import { GuestShell } from "@/components/guest-shell";

export default function HomePage() {
  return (
    <GuestShell>
      <GuestHome />
    </GuestShell>
  );
}
