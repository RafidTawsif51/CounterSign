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
  { to: "/", label: "Payment run", icon: Banknote, key: "P", end: true },
  { to: "/inbox", label: "Inbox", icon: Inbox, key: "I", liveOnly: true },
  { to: "/attack", label: "Attack console", icon: Crosshair, key: "A", liveOnly: true },
  { to: "/leaderboard", label: "Leaderboard", icon: ListOrdered, key: "L", newTab: true },
  { to: "/red-team", label: "Red team", icon: FlaskConical, key: "T" },
  { to: "/status", label: "System status", icon: Activity, key: "S" },
  { to: "/about", label: "About Countersign", icon: BookOpen, key: "O" },
];

/** The screens to offer: in a replay, only the ones that can run from the recording. */
export function useVisibleNav(): NavItem[] {
  const mode = useDataMode();
  return mode === "replay" ? NAV.filter((n) => !n.liveOnly) : NAV;
}
