import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { TECHNIQUES } from "@/lib/risk-catalog";
import type { InjectionFinding } from "@/lib/types";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

// The original stored PDF (GET /api/invoices/{id}/pdf), drawn by pdf.js, with a box over every hidden-text finding.
// The PDF is untrusted: no scripts, no eval. Box coordinates are PDF points from the top left, as the API sends them.

const MAX_PAGES = 5;
/** Room to the right of the page for boxes of off-page text, which keep their real coordinates. */
const GUTTER = 150;

type Status = "loading" | "ready" | "error";

export function PdfView({
  url,
  findings,
  reveal,
  width,
  onError,
}: {
  url: string;
  findings: InjectionFinding[];
  reveal: boolean;
  /** Width available for the page, in CSS px. */
  width: number;
  onError: () => void;
}) {
  const [doc, setDoc] = useState<pdfjs.PDFDocumentProxy | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const failed = useRef(onError);
  failed.current = onError;

  useEffect(() => {
    setStatus("loading");
    const task = pdfjs.getDocument({ url, isEvalSupported: false, enableXfa: false, disableAutoFetch: true });
    let alive = true;
    task.promise.then(
      (d) => {
        if (!alive) return void d.destroy();
        setDoc(d);
        setStatus("ready");
      },
      () => {
        if (!alive) return;
        setStatus("error");
        failed.current();
      },
    );
    return () => {
      alive = false;
      void task.destroy();
    };
  }, [url]);

  if (status === "loading") return <p className="py-10 text-center text-sm text-ink-muted">Loading the invoice PDF…</p>;
  if (status === "error" || !doc) return null;
  const pages = Math.min(doc.numPages, MAX_PAGES);
  return (
    <div className="flex flex-col items-center gap-4">
      {Array.from({ length: pages }, (_, i) => (
        <PdfPage key={i} doc={doc} pageNumber={i + 1} width={width} reveal={reveal} findings={findings.filter((f) => f.page === i + 1 && f.bbox)} />
      ))}
      {doc.numPages > MAX_PAGES && <p className="text-xs text-ink-muted">Showing the first {MAX_PAGES} of {doc.numPages} pages.</p>}
    </div>
  );
}

function PdfPage({ doc, pageNumber, width, reveal, findings }: { doc: pdfjs.PDFDocumentProxy; pageNumber: number; width: number; reveal: boolean; findings: InjectionFinding[] }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState<{ w: number; h: number; scale: number } | null>(null);
  const offPage = findings.some((f) => f.technique === "off_page");
  const gutter = reveal && offPage ? GUTTER : 0;

  useEffect(() => {
    let alive = true;
    let task: pdfjs.RenderTask | null = null;
    void doc.getPage(pageNumber).then((page) => {
      if (!alive || !canvas.current) return;
      const base = page.getViewport({ scale: 1 });
      const scale = Math.max(0.3, (width - gutter) / base.width);
      const dpr = window.devicePixelRatio || 1;
      const viewport = page.getViewport({ scale: scale * dpr });
      const el = canvas.current;
      el.width = viewport.width;
      el.height = viewport.height;
      setSize({ w: base.width * scale, h: base.height * scale, scale });
      task = page.render({ canvasContext: el.getContext("2d")!, viewport });
      task.promise.catch(() => {});
    });
    return () => {
      alive = false;
      task?.cancel();
    };
  }, [doc, pageNumber, width, gutter]);

  return (
    <div className="relative bg-white shadow-sm" style={{ width: size?.w ?? width, height: size?.h ?? 0, marginRight: gutter }} aria-label={`Page ${pageNumber} of the invoice PDF`}>
      <canvas ref={canvas} style={{ width: size?.w, height: size?.h }} className="block" />
      {reveal && size && findings.map((f) => <Box key={f.id} finding={f} scale={size.scale} pageWidth={size.w} />)}
    </div>
  );
}

function Box({ finding, scale, pageWidth }: { finding: InjectionFinding; scale: number; pageWidth: number }) {
  const [x0, top, x1, bottom] = finding.bbox!;
  // Clip to the gutter beside the page: off-page text starts past the right edge and can run a thousand points on.
  const left = Math.max(-GUTTER, x0 * scale);
  const right = Math.min(pageWidth + GUTTER, x1 * scale);
  const off = x1 * scale > pageWidth + GUTTER || x0 * scale > pageWidth;
  const label = TECHNIQUES[finding.technique] ?? finding.technique;
  // The hidden words themselves, legible in ink on an opaque fill over the PDF (on the page they are white on white, tiny or off
  // the edge). The box keeps the finding's position and width and grows downward to fit the text. Untrusted text: plain text only.
  return (
    <div
      className="pointer-events-none absolute rounded-[2px] border-2 border-blocked bg-surface px-1.5 py-1"
      style={{ left, top: top * scale - 2, width: Math.max(160, right - left), minHeight: Math.max(6, (bottom - top) * scale + 4) }}
      title={`${label}: ${finding.snippet}`}
    >
      <span className="absolute -top-5 left-0 whitespace-nowrap rounded-sm bg-blocked px-1 text-[10px] leading-4 font-medium text-white">
        {label}, {Math.round(finding.confidence * 100)}% confidence
        {off ? " \u2192" : ""}
      </span>
      {/* Account and routing numbers in the attacker's text keep their last four only (DESIGN.md: no full account numbers). */}
      <span className="block text-[11px] leading-[1.35] text-blocked-ink">{finding.snippet.replace(/\d{5,}/g, (m) => `\u2022\u2022\u2022\u2022 ${m.slice(-4)}`)}</span>
    </div>
  );
}
