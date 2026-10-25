import { useState } from "react";
import { Outlet } from "react-router-dom";
import { AdminKeyDialog } from "@/components/shared/admin-key-dialog";
import { CommandPalette } from "@/components/shared/command-palette";
import { DemoShortcuts } from "@/components/shared/demo-shortcuts";
import { OfflineBanner } from "@/components/shared/offline-demo";
import { ReplayBanner } from "@/components/shared/replay-banner";
import { RunProvider } from "@/components/shared/run-context";
import { Sidebar } from "@/components/shared/sidebar";
import { TopBar } from "@/components/shared/top-bar";
import { useConnectionMonitor } from "@/lib/connection";
import { usePresenting } from "@/lib/presentation";

export function AppShell() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const presenting = usePresenting();
  useConnectionMonitor();

  return (
    <RunProvider>
      <div className="flex min-h-[calc(100vh/var(--present-zoom))] bg-paper text-ink">
        {!presenting && <Sidebar />}
        <div className="flex min-w-0 flex-1 flex-col">
          <TopBar
            onOpenPalette={() => setPaletteOpen(true)}
            onOpenShortcuts={() => setShortcutsOpen(true)}
            resetOpen={resetOpen}
            onResetOpenChange={setResetOpen}
          />
          <OfflineBanner />
          <ReplayBanner />
          <main className="flex-1">
            <Outlet />
          </main>
        </div>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <AdminKeyDialog />
      <DemoShortcuts helpOpen={shortcutsOpen} onHelpOpenChange={setShortcutsOpen} onReset={() => setResetOpen(true)} />
    </RunProvider>
  );
}
