import { useEffect, useRef, type Dispatch, type SetStateAction } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { isGoChordPending } from "@/components/shared/command-palette";
import { Kbd, modKey } from "@/components/shared/kbd";
import { NAV } from "@/components/shared/nav";
import { useCurrentRun } from "@/components/shared/run-context";
import { errorMessage } from "@/lib/api-error";
import { setPresenting } from "@/lib/presentation";

// Single-key shortcuts for running the demo on stage. They never fire while typing, with a modifier held, or as the
// second key of the palette's G chord. With a dialog or the drawer open, only F and ? work.

type Action = "start" | "reset" | "attack" | "leaderboard" | "present" | "help";

const DEMO: { key: string; action: Action; label: string }[] = [
  { key: "S", action: "start", label: "Start the payment run" },
  { key: "R", action: "reset", label: "Reset the demo, after you confirm" },
  { key: "A", action: "attack", label: "Open the attack console" },
  { key: "L", action: "leaderboard", label: "Open the leaderboard in a new window" },
  { key: "F", action: "present", label: "Presentation mode: hide the sidebar, type 1.15x" },
  { key: "?", action: "help", label: "Show these shortcuts" },
];

const ALWAYS: Action[] = ["present", "help"];

function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  return Boolean(el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)));
}

const dialogOpen = () => document.querySelector('[role="dialog"], [role="alertdialog"]') !== null;

export function openLeaderboardWindow() {
  // A named popup: pressing L again focuses the same window instead of opening another. It inherits this tab's
  // session, so it starts in the same live or offline mode.
  const win = window.open("/leaderboard", "countersign-leaderboard", "popup,width=1280,height=800");
  if (win) win.focus();
  else toast.error("Leaderboard window blocked", { description: "Allow pop-ups for this site, or open it from the sidebar." });
}

export function DemoShortcuts({
  helpOpen,
  onHelpOpenChange,
  onReset,
}: {
  helpOpen: boolean;
  onHelpOpenChange: Dispatch<SetStateAction<boolean>>;
  onReset: () => void;
}) {
  const navigate = useNavigate();
  const { runId, summary, runFailed, startRun } = useCurrentRun();
  const running = Boolean(runId) && !summary.completed && !runFailed;
  const starting = useRef(false);

  // Read through a ref so the listener is attached once and still sees the current run.
  const act = useRef<(a: Action) => void>(() => {});
  act.current = (action) => {
    switch (action) {
      case "start":
        navigate("/");
        if (running || starting.current) {
          toast("The payment run is already in progress");
          return;
        }
        starting.current = true;
        startRun()
          .catch((err) => toast.error("Payment run not started", { description: errorMessage(err) }))
          .finally(() => (starting.current = false));
        return;
      case "reset":
        onReset();
        return;
      case "attack":
        navigate("/attack");
        return;
      case "leaderboard":
        openLeaderboardWindow();
        return;
      case "present": {
        const on = !document.documentElement.hasAttribute("data-presenting");
        setPresenting(on);
        toast(on ? "Presentation mode on" : "Presentation mode off", { description: on ? "Press F to leave." : undefined });
        return;
      }
      case "help":
        onHelpOpenChange((o) => !o);
        return;
    }
  };

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented || e.repeat || e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTyping(e.target) || isGoChordPending()) return;
      // "?" needs Shift on most layouts; the letters are plain keys only.
      const item = e.key === "?" ? DEMO.find((d) => d.key === "?") : e.shiftKey ? undefined : DEMO.find((d) => d.key === e.key.toUpperCase());
      if (!item) return;
      if (!ALWAYS.includes(item.action) && dialogOpen()) return;
      e.preventDefault();
      act.current(item.action);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <Dialog open={helpOpen} onOpenChange={onHelpOpenChange}>
      <DialogContent className="max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>Single keys work anywhere outside a text field.</DialogDescription>
        </DialogHeader>
        <ShortcutList
          title="Running the demo"
          rows={DEMO.map((d) => ({ keys: [d.key], label: d.label }))}
        />
        <ShortcutList
          title="Getting around"
          rows={[
            { keys: [modKey, "K"], label: "Search pages, vendors and payments" },
            ...NAV.map((n) => ({ keys: ["G", n.key], label: n.label })),
          ]}
        />
      </DialogContent>
    </Dialog>
  );
}

function ShortcutList({ title, rows }: { title: string; rows: { keys: string[]; label: string }[] }) {
  return (
    <section>
      <h3 className="mb-1 text-sm font-medium text-ink-muted">{title}</h3>
      <dl className="divide-y divide-rule border-y border-rule">
        {rows.map((r) => (
          <div key={r.keys.join("+") + r.label} className="flex h-9 items-center gap-4">
            <dt className="flex w-12 shrink-0 items-center gap-1">
              {r.keys.map((k) => (
                <Kbd key={k}>{k}</Kbd>
              ))}
            </dt>
            <dd className="min-w-0 truncate text-sm">{r.label}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
