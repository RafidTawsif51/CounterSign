import { useDataMode } from "@/lib/data-mode";
import { Activity, Banknote, BookOpen, Crosshair, FlaskConical, Inbox, ListOrdered, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Second key after G, for the go-to shortcut. */
  key: string;
  end?: boolean;
  newTab?: boolean;
  /** Needs the live server: not part of a replay. */
  liveOnly?: boolean;
}

export const NAV: NavItem[] = [
  { to: "/app", label: "Payment run", icon: Banknote, key: "P", end: true },
  { to: "/app/inbox", label: "Inbox", icon: Inbox, key: "I", liveOnly: true },
  { to: "/app/attack", label: "Attack console", icon: Crosshair, key: "A", liveOnly: true },
  { to: "/app/leaderboard", label: "Leaderboard", icon: ListOrdered, key: "L", newTab: true },
  { to: "/app/red-team", label: "Red team", icon: FlaskConical, key: "T" },
  { to: "/app/status", label: "System status", icon: Activity, key: "S" },
  { to: "/", label: "About Countersign", icon: BookOpen, key: "O", end: true },
];

/** The screens to offer: in a replay, only the ones that can run from the recording. */
export function useVisibleNav(): NavItem[] {
  const mode = useDataMode();
  return mode === "replay" ? NAV.filter((n) => !n.liveOnly) : NAV;
}
