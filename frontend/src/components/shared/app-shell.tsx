import { useState } from "react";
import { Outlet } from "react-router-dom";
import { CommandPalette } from "@/components/shared/command-palette";
import { RunProvider } from "@/components/shared/run-context";
import { Sidebar } from "@/components/shared/sidebar";
import { TopBar } from "@/components/shared/top-bar";

export function AppShell() {
  const [paletteOpen, setPaletteOpen] = useState(false);

  return (
    <RunProvider>
      <div className="flex min-h-screen bg-paper text-ink">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar onOpenPalette={() => setPaletteOpen(true)} />
          <main className="flex-1">
            <Outlet />
          </main>
        </div>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </RunProvider>
  );
}
