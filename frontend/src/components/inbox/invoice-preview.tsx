import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { iconProps } from "@/components/shared/icon";
import { formatAccount, formatDate, formatUSD } from "@/lib/format";
import { TECHNIQUES } from "@/lib/risk-catalog";
import type { HistoryInvoice, InjectionFinding, Vendor } from "@/lib/types";
import { cn } from "@/lib/utils";

// Invoice preview with "Reveal hidden content". The API does not serve the original PDF yet, so the page is rebuilt
// from the stored invoice at US Letter size (612 x 792 pt). Hidden text is drawn where the seed's PDF generator puts it
// for each technique (backend/seed/invoice_pdf.py): white text at the left margin 70 pt from the bottom, tiny font at
// 62 pt, off-page text starting past the right edge. Unrevealed, white text is white on white, as in the PDF.

// The document's own colors, not UI tokens: a PDF page is white paper with near-black type in any theme.
const PAPER = "#ffffff";
const PRINT = "#1a1a1a";
const PAGE_W = 612;
const PAGE_H = 792;
const L = 50; // left margin, pt

export function InvoicePreview({
  open,
  onOpenChange,
  name,
  invoice,
  vendor,
  findings,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  name: string;
  invoice: HistoryInvoice;
  vendor: Vendor;
  findings: InjectionFinding[];
}) {
  const [reveal, setReveal] = useState(false);
  useEffect(() => {
    if (!open) setReveal(false);
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] max-w-[720px] grid-rows-[auto_1fr_auto] overflow-hidden p-0">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-rule px-5 py-3 pr-12">
          <div className="min-w-0 flex-1">
            <DialogTitle className="figure truncate text-md font-medium">{name}</DialogTitle>
            <DialogDescription className="text-sm text-ink-muted">
              {vendor.name}, {formatUSD(invoice.amount_usd)}
            </DialogDescription>
          </div>
          {findings.length > 0 ? (
            <Button variant={reveal ? "primary" : "secondary"} size="sm" aria-pressed={reveal} onClick={() => setReveal((r) => !r)}>
              {reveal ? <EyeOff {...iconProps} /> : <Eye {...iconProps} />}
              {reveal ? "Hide hidden content" : "Reveal hidden content"}
            </Button>
          ) : (
            <span className="text-sm text-ink-muted">No hidden content found in this invoice</span>
          )}
        </div>

        <div className="min-h-0 overflow-auto bg-sunken px-5 py-5">
          <Page invoice={invoice} vendor={vendor} findings={findings} reveal={reveal} />
        </div>

        <p className="border-t border-rule px-5 py-2.5 text-xs text-ink-muted">
          Rebuilt from the stored invoice; the API does not serve the original PDF yet. Hidden text sits where the PDF draws it.
        </p>
      </DialogContent>
    </Dialog>
  );
}

/** The page at true size in pt, scaled to the dialog width. Off-page text can spill past the right edge. */
function Page({ invoice, vendor, findings, reveal }: { invoice: HistoryInvoice; vendor: Vendor; findings: InjectionFinding[]; reveal: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const offPage = findings.some((f) => f.technique === "off_page");

  // Fit the whole page in view, width and height, so hidden text near the bottom is on screen when revealed.
  useEffect(() => {
    const el = box.current?.parentElement;
    if (!el) return;
    const fit = () => {
      const w = el.clientWidth - 40;
      const h = el.clientHeight - 40;
      setScale(Math.min(1, w / (PAGE_W + (offPage && reveal ? 140 : 0)), h / PAGE_H));
    };
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    fit();
    return () => ro.disconnect();
  }, [offPage, reveal]);

  const remit = invoice.remittance as { bank_name?: string; account_last4?: string } | null;
  const at = (top: number, left = L, extra?: CSSProperties): CSSProperties => ({ position: "absolute", top, left, ...extra });

  return (
    <div ref={box} className="flex w-full justify-center">
      <div style={{ width: PAGE_W * scale, height: PAGE_H * scale }}>
        <div
          // Clipped like paper until revealed, so off-page text stays off the page.
          className={cn("relative origin-top-left border border-rule", reveal ? "overflow-visible" : "overflow-hidden")}
          style={{
            width: PAGE_W,
            height: PAGE_H,
            transform: `scale(${scale})`,
            background: PAPER,
            color: PRINT,
            fontFamily: "Helvetica, Arial, sans-serif",
            fontSize: 10,
          }}
          aria-label={`Invoice ${invoice.number ?? ""} from ${vendor.name}`}
        >
          <div style={at(48)} className="text-[20px] font-bold">
            {vendor.name}
          </div>
          <div style={at(74, L, { fontSize: 8, opacity: 0.7 })}>{vendor.email_domain}</div>

          <dl style={at(48, 380)} className="grid grid-cols-[72px_1fr] gap-y-1">
            <dt>Invoice #:</dt>
            <dd>{invoice.number}</dd>
            <dt>Due date:</dt>
            <dd>{formatDate(invoice.due_date)}</dd>
          </dl>

          <div style={at(130)}>
            <span className="font-bold">Bill to:</span> Ridgeline Builders
          </div>

          <table style={at(170, L, { width: PAGE_W - 2 * L })} className="border-collapse">
            <thead>
              <tr className="border-b border-[#999] text-left">
                <th className="py-1 font-bold">Item</th>
                <th className="py-1 font-bold">Description</th>
                <th className="py-1 text-right font-bold">Amount</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="py-1">1.</td>
                <td className="py-1">{sentence(`${vendor.trade} materials and services`)}</td>
                <td className="py-1 text-right">{formatUSD(invoice.amount_usd)}</td>
              </tr>
            </tbody>
          </table>
          <div style={at(232, PAGE_W - L - 200, { width: 200 })} className="space-y-1 text-right">
            <div>Subtotal: {formatUSD(invoice.amount_usd)}</div>
            <div className="text-[11px] font-bold">Total due: {formatUSD(invoice.amount_usd)}</div>
          </div>

          <div style={at(300)} className="space-y-1">
            <div className="font-bold">Remit to</div>
            <div>{remit?.bank_name ?? "Bank on file"}</div>
            {/* Never more than the last four digits, even on a facsimile. */}
            <div>Account {formatAccount(remit?.account_last4)}</div>
          </div>

          <div style={at(PAGE_H - 40 - 7, L, { fontSize: 7, opacity: 0.55 })}>
            Please reference the invoice number with your remittance.
          </div>

          {findings.map((f) => (
            <Hidden key={f.id} finding={f} reveal={reveal} />
          ))}
        </div>
      </div>
    </div>
  );
}

/** One finding, drawn where its technique hides it. Revealed: outlined in place, text legible, technique labelled. */
function Hidden({ finding, reveal }: { finding: InjectionFinding; reveal: boolean }) {
  const label = `${TECHNIQUES[finding.technique]}, ${Math.round(finding.confidence * 100)}% confidence`;
  // Positions in pt from the top-left, mirroring invoice_pdf.py (which measures from the bottom).
  const place: Record<string, { top: number; left: number; width: number; font: number; note: string }> = {
    white_text: { top: PAGE_H - 70 - 8, left: L, width: 470, font: 8, note: "White text on a white page" },
    tiny_font: { top: PAGE_H - 62 - 2, left: L, width: 470, font: 1.2, note: "1.2 pt text" },
    off_page: { top: PAGE_H - 300 - 10, left: 640, width: 360, font: 10, note: "Drawn past the page edge" },
  };
  const p = place[finding.technique];

  // Techniques with no position on the page (zero-width characters, the instruction classifier) sit in the text layer.
  if (!p)
    return (
      <Revealable reveal={reveal} label={label} note="Hidden in the PDF text layer, not drawn on the page" style={{ top: 14, left: L, width: PAGE_W - 2 * L }}>
        <span style={{ fontSize: 8 }}>{finding.snippet}</span>
      </Revealable>
    );

  const tiny = finding.technique === "tiny_font";
  return (
    <Revealable reveal={reveal} label={label} note={p.note} style={{ top: p.top, left: p.left, width: p.width }}>
      {/* Untrusted text: plain text only. White on white until revealed, exactly as the PDF hides it. */}
      <span
        className="block leading-[1.25] transition-colors duration-150"
        style={{ fontSize: reveal && tiny ? 8 : p.font, color: !reveal && finding.technique === "white_text" ? PAPER : undefined }}
      >
        {finding.snippet}
      </span>
    </Revealable>
  );
}

function Revealable({ reveal, label, note, style, children }: { reveal: boolean; label: string; note: string; style: CSSProperties; children: ReactNode }) {
  return (
    <div style={{ position: "absolute", ...style }}>
      <div
        className={cn(
          "pointer-events-none absolute bottom-full left-[-3px] mb-1 flex items-center gap-2 rounded-sm bg-blocked px-2 py-0.5 font-sans text-[11px] font-medium whitespace-nowrap text-accent-ink transition-opacity duration-150",
          reveal ? "opacity-100" : "opacity-0",
        )}
        aria-hidden={!reveal}
      >
        <span>{label}</span>
        <span className="font-normal opacity-90">{note}</span>
      </div>
      <div
        className={cn(
          "-m-[3px] rounded-sm p-[3px] outline-2 outline-solid transition-[outline-color,background-color,color] duration-150",
          reveal ? "bg-blocked-tint text-blocked-ink outline-blocked" : "outline-transparent",
        )}
      >
        {children}
      </div>
      {reveal && <span className="sr-only">Hidden content revealed: {label}. {note}.</span>}
    </div>
  );
}

const sentence = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);
