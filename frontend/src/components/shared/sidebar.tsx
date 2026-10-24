import { useEffect, useState } from "react";
import { Link, useMatch, useResolvedPath } from "react-router-dom";
import { ArrowUpRight, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { CountersignMark } from "@/components/shared/countersign-mark";
import { iconProps } from "@/components/shared/icon";
import { NAV, type NavItem } from "@/components/shared/nav";
import { cn } from "@/lib/utils";

const STORAGE_KEY = "countersign-sidebar-collapsed";

function readCollapsed() {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(readCollapsed);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
    } catch {
      // Not remembered across visits; the toggle still works.
    }
  }, [collapsed]);

  return (
    <aside
      data-collapsed={collapsed}
      className={cn(
        "group/sidebar sticky top-0 flex h-screen shrink-0 flex-col border-r border-rule bg-paper transition-[width] duration-200",
        // Phones always get the icon rail.
        "w-14",
        !collapsed && "md:w-[220px]",
      )}
    >
      <div className="flex h-12 shrink-0 items-center gap-2.5 border-b border-rule px-[18px]">
        <CountersignMark />
        <span className={cn("hidden font-semibold tracking-[-0.01em]", !collapsed && "md:inline")}>Countersign</span>
      </div>

      <nav aria-label="Main" className="flex flex-1 flex-col gap-0.5 p-2">
        {NAV.map((item) => (
          <SidebarLink key={item.to} item={item} collapsed={collapsed} />
        ))}
      </nav>

      <div className="hidden border-t border-rule p-2 md:block">
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="flex h-8 w-full items-center gap-2.5 rounded-md px-2.5 text-sm text-ink-muted transition-colors hover:bg-sunken hover:text-ink"
        >
          {collapsed ? <PanelLeftOpen {...iconProps} /> : <PanelLeftClose {...iconProps} />}
          {!collapsed && "Collapse"}
        </button>
      </div>
    </aside>
  );
}

function SidebarLink({ item, collapsed }: { item: NavItem; collapsed: boolean }) {
  const Icon = item.icon;
  // Active state computed here, not via NavLink's className function: TooltipTrigger asChild merges className as a string.
  const path = useResolvedPath(item.to);
  const isActive = useMatch({ path: path.pathname, end: item.end ?? false }) !== null;
  const base =
    "relative flex h-8 items-center gap-2.5 rounded-md border border-transparent px-2.5 text-base whitespace-nowrap transition-colors hover:bg-sunken";
  const label = <span className={cn("hidden min-w-0 flex-1 truncate", !collapsed && "md:inline")}>{item.label}</span>;

  const link = item.newTab ? (
    <a href={item.to} target="_blank" rel="noreferrer" className={cn(base, "text-ink-muted hover:text-ink")}>
      <Icon {...iconProps} />
      {label}
      <ArrowUpRight {...iconProps} className={cn("hidden text-ink-faint", !collapsed && "md:block")} />
    </a>
  ) : (
    <Link
      to={item.to}
      aria-current={isActive ? "page" : undefined}
      className={cn(
        base,
        isActive
          ? "border-rule bg-surface font-medium text-ink before:absolute before:inset-y-1.5 before:-left-px before:w-0.5 before:bg-accent"
          : "text-ink-muted hover:text-ink",
      )}
    >
      <Icon {...iconProps} />
      {label}
    </Link>
  );

  // In the icon rail, the label moves into a tooltip.
  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right" className={cn(!collapsed && "md:hidden")}>
        {item.label}
        {item.newTab && ", opens in a new tab"}
      </TooltipContent>
    </Tooltip>
  );
}
