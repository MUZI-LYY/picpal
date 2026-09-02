import type { ReactNode } from "react";
import { InviteGate } from "@/components/invite-gate";

export default function PlanLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <InviteGate>{children}</InviteGate>;
}
