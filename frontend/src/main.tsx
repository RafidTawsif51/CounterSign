import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "framer-motion";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "./styles/globals.css";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { getDataMode, setDataMode, subscribeDataMode } from "@/lib/data-mode";
import { loadRecording } from "@/lib/replay";
import { App } from "./App";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 10_000, retry: 1, refetchOnWindowFocus: false },
  },
});

// Cached answers belong to the server or to the mock. On the offline-demo switch (either way), refetch everything.
subscribeDataMode(() => void queryClient.resetQueries());

async function boot() {
  // A reload in the middle of a replay keeps the mode but not the recording: load it first, or go back to live.
  if (getDataMode() === "replay") await loadRecording().catch(() => setDataMode("live"));
  render();
}

function render() {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        {/* framer-motion honors prefers-reduced-motion everywhere. */}
        <MotionConfig reducedMotion="user" transition={{ duration: 0.18, ease: [0.2, 0, 0, 1] }}>
          <TooltipProvider>
            <App />
            <Toaster />
          </TooltipProvider>
        </MotionConfig>
      </QueryClientProvider>
    </StrictMode>,
  );
}

void boot();
