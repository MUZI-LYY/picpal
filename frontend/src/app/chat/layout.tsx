import type { ReactNode } from "react";
import { InviteGate } from "@/components/invite-gate";

export default function ChatLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <InviteGate>{children}</InviteGate>;
}
