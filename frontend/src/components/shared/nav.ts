import { Activity, Banknote, Crosshair, FlaskConical, Inbox, ListOrdered, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Second key after G, for the go-to shortcut. */
  key: string;
  end?: boolean;
  newTab?: boolean;
}

export const NAV: NavItem[] = [
  { to: "/", label: "Payment run", icon: Banknote, key: "P", end: true },
  { to: "/inbox", label: "Inbox", icon: Inbox, key: "I" },
  { to: "/attack", label: "Attack console", icon: Crosshair, key: "A" },
  { to: "/leaderboard", label: "Leaderboard", icon: ListOrdered, key: "L", newTab: true },
  { to: "/red-team", label: "Red team", icon: FlaskConical, key: "T" },
  { to: "/status", label: "System status", icon: Activity, key: "S" },
];
