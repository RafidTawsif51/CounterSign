import { NavLink, Outlet } from "react-router-dom";
import { MonitorUp } from "lucide-react";
import { iconProps } from "@/components/shared/icon";
import { USE_MOCKS } from "@/lib/api";
import { cn } from "@/lib/utils";

const nav = [
  { to: "/", label: "Payment run", end: true },
  { to: "/inbox", label: "Inbox" },
  { to: "/attack", label: "Attack console" },
  { to: "/red-team", label: "Red team" },
  { to: "/status", label: "System status" },
];

export function AppShell() {
  return (
    <div className="flex min-h-screen flex-col bg-paper text-ink">
      <header className="border-b border-rule bg-paper">
        <div className="flex h-12 items-stretch gap-6 overflow-x-auto px-4 sm:px-6">
          <div className="flex shrink-0 items-center gap-2">
            <span className="font-semibold">Countersign</span>
            <span className="hidden text-sm text-ink-muted sm:inline">Ridgeline Builders</span>
          </div>
          <nav aria-label="Main" className="flex items-stretch gap-5">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    "-mb-px flex items-center border-b-2 text-base whitespace-nowrap transition-colors",
                    isActive ? "border-accent text-ink" : "border-transparent text-ink-muted hover:text-ink",
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-4">
            {USE_MOCKS && <span className="text-sm text-held-ink">Mock data</span>}
            <a
              href="/leaderboard"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-sm whitespace-nowrap text-ink-muted hover:text-ink"
            >
              <MonitorUp {...iconProps} />
              Open leaderboard
            </a>
          </div>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  );
}
