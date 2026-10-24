import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { QRCodeSVG } from "qrcode.react";
import { ShieldCheck } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { NumberTicker } from "@/components/board/number-ticker";
import { iconProps } from "@/components/shared/icon";
import { InlineError } from "@/components/shared/inline-error";
import { BOUNTY_EMAIL, api } from "@/lib/api";
import { subscribeLeaderboard } from "@/lib/events";
import { formatClock, formatUSD } from "@/lib/format";
import type { AttackLoggedEvent, LeaderboardRow } from "@/lib/types";
import { cn } from "@/lib/utils";

// Rob Countersign: the second screen across the table. Always dark. Every attempt from the attack console, judges and
// the bounty inbox, live; a miss is never hidden, it becomes a new test case. ?tv=1 is for the TV: 1.5x type, a
// periodic refresh as a safety net under the live stream, and the cursor out of the way.

const SOURCE: Record<string, string> = { console: "Console", judge: "Judge", bounty_email: "Email bounty" };
const CARD: Record<string, string> = {
  classic_bank_change: "We changed banks",
  poisoned_invoice: "Poisoned invoice",
  ai_hijack: "Poisoned invoice",
  ceo_pressure: "CEO pressure",
  freestyle: "Freestyle",
};

export function Leaderboard() {
  const [params] = useSearchParams();
  const tv = params.get("tv") === "1";
  const queryClient = useQueryClient();
  const board = useQuery({ queryKey: ["leaderboard"], queryFn: api.leaderboard, refetchInterval: tv ? 10_000 : false });
  // Attempts seen on the stream before the next fetch includes them, by attack id.
  const [live, setLive] = useState<Map<string, AttackLoggedEvent>>(new Map());
  const idle = useIdleCursor(tv);

  useEffect(() => {
    let dropped = false;
    return subscribeLeaderboard(
      (e) => {
        if (e.moderation_status === "hidden") return;
        setLive((m) => new Map(m).set(e.attack_id, e));
        // A result can move money; the totals come from the server.
        if (e.result) void queryClient.invalidateQueries({ queryKey: ["leaderboard"] });
      },
      (s) => {
        // The leaderboard stream does not replay, so attempts made while it was down come from a fresh fetch.
        if (s === "reconnecting") dropped = true;
        if (s === "live" && dropped) {
          dropped = false;
          void queryClient.invalidateQueries({ queryKey: ["leaderboard"] });
        }
      },
    );
  }, [queryClient]);

  const rows = useMemo(() => merge(board.data?.attempts ?? [], live), [board.data, live]);
  const totals = board.data?.totals;
  const attackers = useMemo(() => new Set(rows.map((r) => r.handle.toLowerCase())).size, [rows]);

  return (
    <div
      data-theme="dark"
      className={cn("min-h-screen bg-paper text-ink", idle && "cursor-none")}
      // zoom scales the px-based type scale and spacing together, which a root font size would not.
      style={tv ? { zoom: 1.5 } : undefined}
    >
      <header className="flex flex-wrap items-start justify-between gap-x-10 gap-y-6 border-b border-rule px-8 pt-8 pb-7">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold">Rob Countersign</h1>
          <p className="mt-1 text-md text-ink-muted">Try to get our AI to pay the wrong account. Every attempt runs live, in sandbox money.</p>
          <dl className="mt-6 flex flex-wrap items-end gap-x-10 gap-y-4">
            <Stat label="Money moved to attackers">
              <NumberTicker value={totals?.sandbox_usd_moved ?? 0} format={formatUSD} className="text-2xl font-medium" />
            </Stat>
            <Stat label="Attempts">
              <NumberTicker value={Math.max(rows.length, totals?.attempts ?? 0)} className="text-xl" />
            </Stat>
            <Stat label="Unique attackers">
              <NumberTicker value={Math.max(attackers, totals?.unique_attackers ?? 0)} className="text-xl" />
            </Stat>
          </dl>
        </div>
        {BOUNTY_EMAIL && <BountyCorner email={BOUNTY_EMAIL} />}
      </header>

      <main className="px-8 pb-10">
        {board.isLoading ? (
          <TableSkeleton />
        ) : board.isError && rows.length === 0 ? (
          <InlineError what="The leaderboard" error={board.error} onRetry={() => void board.refetch()} retrying={board.isFetching} className="py-8 text-md" />
        ) : rows.length === 0 ? (
          <p className="py-8 text-md text-ink-muted">No attempts yet. Open the attack console{BOUNTY_EMAIL ? " or email the bounty inbox" : ""} and try.</p>
        ) : (
          <AttemptTable rows={rows} />
        )}
      </main>
    </div>
  );
}

/** Server rows, with stream-only attempts added on top and fresher stream results applied. */
function merge(rows: LeaderboardRow[], live: Map<string, AttackLoggedEvent>): LeaderboardRow[] {
  const byId = new Map(rows.map((r) => [r.id, r]));
  const extra: LeaderboardRow[] = [];
  for (const e of live.values()) {
    const known = byId.get(e.attack_id);
    if (known) {
      if (!known.result && e.result) byId.set(e.attack_id, { ...known, result: e.result });
      continue;
    }
    extra.push({
      id: e.attack_id,
      handle: e.attacker_name,
      source: e.source,
      card: e.card,
      result: e.result,
      outcome: "processing",
      top_reasons: [],
      amount_usd: null,
      paid_usd: 0,
      created_at: e.at,
      moderation_status: e.moderation_status,
      text: null,
    });
  }
  return [...extra, ...rows.map((r) => byId.get(r.id)!)].sort((a, b) => (a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0));
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-sm text-ink-muted">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  );
}

function AttemptTable({ rows }: { rows: LeaderboardRow[] }) {
  return (
    <table className="mt-2 w-full border-collapse text-left">
      <thead>
        <tr className="h-12 border-b border-rule text-sm text-ink-muted">
          <th className="pr-4 font-medium">Attacker</th>
          <th className="px-4 font-medium">Source</th>
          <th className="px-4 font-medium">Attack</th>
          <th className="px-4 font-medium">Result</th>
          <th className="pl-4 text-right font-medium">Time</th>
        </tr>
      </thead>
      <tbody>
        <AnimatePresence initial={false}>
          {rows.map((r) => (
            <motion.tr
              key={r.id}
              layout="position"
              initial={{ opacity: 0, y: -16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}
              className={cn("border-b border-rule", r.result === "missed" && "bg-sunken")}
            >
              <td className="max-w-80 truncate py-3.5 pr-4 text-md font-medium">{r.handle}</td>
              <td className="px-4 py-3.5 text-ink-muted">{SOURCE[r.source] ?? r.source}</td>
              <td className="px-4 py-3.5">{CARD[r.card] ?? r.card.replace(/_/g, " ")}</td>
              <td className="px-4 py-3.5">
                <Result row={r} />
              </td>
              <td className="figure py-3.5 pl-4 text-right text-ink-muted">{formatClock(r.created_at)}</td>
            </motion.tr>
          ))}
        </AnimatePresence>
      </tbody>
    </table>
  );
}

function Result({ row }: { row: LeaderboardRow }) {
  if (row.result === "caught")
    return (
      <span className="inline-flex items-center gap-2 text-md font-semibold">
        <ShieldCheck {...iconProps} size={18} />
        Caught
      </span>
    );
  if (row.result === "missed")
    return (
      <span className="flex flex-col">
        <span className="text-md font-semibold">Missed</span>
        <span className="text-sm text-ink-muted">Logged as new test case</span>
      </span>
    );
  return <span className="text-ink-muted">Processing</span>;
}

function BountyCorner({ email }: { email: string }) {
  return (
    <div className="flex items-center gap-5 rounded-lg border border-rule bg-surface p-4">
      {/* Printed-code colors, not theme tokens: scanners need dark modules on a light quiet zone, whatever the theme. */}
      <QRCodeSVG
        value={`mailto:${email}?subject=${encodeURIComponent("Rob Countersign")}`}
        size={128}
        bgColor="#ffffff"
        fgColor="#10151c"
        level="M"
        marginSize={2}
        className="shrink-0 rounded-md"
        aria-label={`QR code: email ${email}`}
      />
      <div className="max-w-56">
        <p className="text-sm text-ink-muted">Email your attack to</p>
        <p className="figure mt-0.5 text-md break-all">{email}</p>
        <p className="mt-2 text-xs text-ink-muted">Sandbox money only. Five tries per sender per hour.</p>
      </div>
    </div>
  );
}

/** On the TV, hide the cursor after 3 s without movement. */
function useIdleCursor(enabled: boolean) {
  const [idle, setIdle] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let t = window.setTimeout(() => setIdle(true), 3000);
    const wake = () => {
      setIdle(false);
      window.clearTimeout(t);
      t = window.setTimeout(() => setIdle(true), 3000);
    };
    window.addEventListener("mousemove", wake);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("mousemove", wake);
    };
  }, [enabled]);
  return enabled && idle;
}

function TableSkeleton() {
  return (
    <div aria-busy className="mt-6 space-y-4">
      {Array.from({ length: 6 }, (_, i) => (
        <Skeleton key={i} className="h-6 w-full" />
      ))}
    </div>
  );
}
