import { useEffect, useMemo, useRef, type Dispatch, type SetStateAction } from "react";
import { useMatch, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Building2, FileText, MessageSquareText } from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command";
import { ASK_PARAM } from "@/components/payment/ask-panel";
import { iconProps } from "@/components/shared/icon";
import { Kbd, modKey } from "@/components/shared/kbd";
import { NAV } from "@/components/shared/nav";
import { useCurrentRun } from "@/components/shared/run-context";
import { StatusBadge } from "@/components/shared/status-badge";
import { api } from "@/lib/api";
import { formatUSD } from "@/lib/format";
import type { PaymentStatus } from "@/lib/types";

interface PaletteProps {
  open: boolean;
  onOpenChange: Dispatch<SetStateAction<boolean>>;
}

export function CommandPalette({ open, onOpenChange }: PaletteProps) {
  const navigate = useNavigate();
  const vendors = useQuery({ queryKey: ["vendors"], queryFn: api.vendors, enabled: open, staleTime: 60_000 });
  const payments = useRunPayments();
  const openPayment = useMatch("/payments/:paymentId")?.params.paymentId ?? null;
  // "Ask why…": the open payment first, then every payment the run held or blocked.
  const askable = [
    ...payments.filter((p) => p.id === openPayment),
    ...payments.filter((p) => p.id !== openPayment && (p.status === "held" || p.status === "blocked")),
  ];

  useGlobalShortcuts(onOpenChange, (to, newTab) => go(to, newTab));

  function go(to: string, newTab = false) {
    onOpenChange(false);
    if (newTab) window.open(to, "_blank", "noreferrer");
    else navigate(to);
  }

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title="Search" description="Go to a page, vendor or payment">
      <CommandInput placeholder="Search pages, vendors and payments" />
      <CommandList>
        <CommandEmpty>No page, vendor or payment matches that.</CommandEmpty>

        {askable.length > 0 && (
          <CommandGroup heading="Ask why…">
            {askable.map((p) => (
              <CommandItem
                key={p.id}
                value={`ask why ${p.vendor} ${p.status}`}
                onSelect={() => go(`/payments/${p.id}?${ASK_PARAM}=1`)}
              >
                <MessageSquareText {...iconProps} />
                <span className="truncate">
                  Ask why… <span className="text-ink-muted">{p.vendor}</span>
                </span>
                {p.status && <StatusBadge status={p.status} className="ml-auto" />}
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        <CommandGroup heading="Pages">
          {NAV.map((item) => (
            <CommandItem key={item.to} value={`page ${item.label}`} onSelect={() => go(item.to, item.newTab)}>
              <item.icon {...iconProps} />
              {item.label}
              <CommandShortcut className="flex gap-1">
                <Kbd>G</Kbd>
                <Kbd>{item.key}</Kbd>
              </CommandShortcut>
            </CommandItem>
          ))}
        </CommandGroup>

        {vendors.data && vendors.data.length > 0 && (
          <CommandGroup heading="Vendors">
            {vendors.data.map((v) => (
              <CommandItem key={v.id} value={`vendor ${v.name} ${v.trade} ${v.email_domain}`} onSelect={() => go(`/inbox?vendor=${v.id}`)}>
                <Building2 {...iconProps} />
                <span className="truncate">{v.name}</span>
                <CommandShortcut className="flex items-center gap-3 font-sans">
                  {v.unverified_requested_accounts > 0 && (
                    <span
                      className="flex items-center gap-1 text-held-ink"
                      title={`${v.unverified_requested_accounts} unverified bank change ${v.unverified_requested_accounts === 1 ? "request" : "requests"}`}
                    >
                      <span aria-hidden className="size-1.5 bg-held" />
                      <span className="figure">{v.unverified_requested_accounts}</span> unverified
                    </span>
                  )}
                  {v.trade}
                </CommandShortcut>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        {payments.length > 0 && (
          <CommandGroup heading="Payments in this run">
            {payments.map((p) => (
              <CommandItem
                key={p.id}
                value={`payment ${p.vendor} ${p.id} ${p.status}`}
                onSelect={() => go(`/payments/${p.id}`)}
              >
                <FileText {...iconProps} />
                <span className="truncate">{p.vendor}</span>
                <span className="ml-auto flex shrink-0 items-center gap-3">
                  {p.status && <StatusBadge status={p.status} />}
                  <span className="figure w-[92px] text-right text-sm">{formatUSD(p.amount)}</span>
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>

      <div className="flex h-9 items-center gap-4 border-t border-rule px-3 text-xs text-ink-muted">
        <span className="flex items-center gap-1.5">
          <Kbd>↑</Kbd>
          <Kbd>↓</Kbd>
          Move
        </span>
        <span className="flex items-center gap-1.5">
          <Kbd>↵</Kbd>
          Open
        </span>
        <span className="flex items-center gap-1.5">
          <Kbd>esc</Kbd>
          Close
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          <Kbd>{modKey}K</Kbd>
          Toggle
        </span>
      </div>
    </CommandDialog>
  );
}

/** Payments the current run has decided on, newest decisions last, with vendor and amount from invoice.parsed. */
function useRunPayments() {
  const { events } = useCurrentRun();
  return useMemo(() => {
    const parsed = new Map<string, { vendor: string; amount: number }>();
    const status = new Map<string, PaymentStatus>();
    for (const e of events) {
      if (e.type === "invoice.parsed") parsed.set(e.payment_id, { vendor: e.vendor, amount: e.amount_usd });
      else if (e.type === "risk.scored") status.set(e.payment_id, status.get(e.payment_id) ?? "pending");
      else if (e.type === "payment.paid") status.set(e.payment_id, "paid");
      else if (e.type === "payment.held") status.set(e.payment_id, "held");
      else if (e.type === "payment.blocked") status.set(e.payment_id, "blocked");
    }
    return [...status].map(([id, st]) => {
      const inv = parsed.get(id);
      return { id, status: st, vendor: inv?.vendor ?? id, amount: inv?.amount ?? null };
    });
  }, [events]);
}

/** Cmd/Ctrl+K toggles the palette. G then a letter jumps to a page, outside text fields. */
function useGlobalShortcuts(onOpenChange: Dispatch<SetStateAction<boolean>>, go: (to: string, newTab?: boolean) => void) {
  const pendingG = useRef<number | null>(null);
  const goRef = useRef(go);
  goRef.current = go;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpenChange((o) => !o);
        return;
      }
      const target = e.target as HTMLElement | null;
      const typing = target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return;

      const key = e.key.toUpperCase();
      if (pendingG.current !== null) {
        window.clearTimeout(pendingG.current);
        pendingG.current = null;
        const item = NAV.find((n) => n.key === key);
        if (item) {
          e.preventDefault();
          goRef.current(item.to, item.newTab);
        }
        return;
      }
      if (key === "G") pendingG.current = window.setTimeout(() => (pendingG.current = null), 1000);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onOpenChange]);
}
