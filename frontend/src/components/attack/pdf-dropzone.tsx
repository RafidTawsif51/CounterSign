import { useRef, useState, type DragEvent } from "react";
import { FileText, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { iconProps } from "@/components/shared/icon";
import { SAMPLE_PDFS } from "@/lib/attack-cards";
import { cn } from "@/lib/utils";

/** What the attack sends as its PDF: a sample file the server already has, or the judge's own, base64. */
export type PdfChoice = { kind: "sample"; file: string; label: string } | { kind: "upload"; name: string; size: number; base64: string };

const MAX_BYTES = 5 * 1024 * 1024; // ingest.MAX_PDF_BYTES

async function readPdf(file: File): Promise<PdfChoice> {
  if (file.size > MAX_BYTES) throw new Error("That PDF is over 5 MB. Try a smaller one.");
  const head = new TextDecoder().decode(await file.slice(0, 5).arrayBuffer());
  if (head !== "%PDF-") throw new Error("That file is not a PDF.");
  const bytes = new Uint8Array(await file.arrayBuffer());
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return { kind: "upload", name: file.name, size: file.size, base64: btoa(bin) };
}

/**
 * `allowUpload` false (mock mode): only the sample can be used, because the mock cannot scan a PDF and would treat any
 * upload as clean. The live backend scans uploads, so they are allowed there.
 */
export function PdfDropzone({
  value,
  onChange,
  allowUpload = true,
}: {
  value: PdfChoice | null;
  onChange: (v: PdfChoice | null) => void;
  allowUpload?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function take(file: File | undefined) {
    if (!file) return;
    setError(null);
    try {
      onChange(await readPdf(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : "That file could not be read.");
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setOver(false);
    if (allowUpload) void take(e.dataTransfer.files[0]);
  }

  const sample = SAMPLE_PDFS[0];
  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (allowUpload) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={cn(
          "rounded-lg border border-dashed px-4 py-5 transition-colors",
          over ? "border-accent bg-accent-tint" : "border-rule-strong bg-paper",
        )}
      >
        {value ? (
          <div className="flex items-center gap-3">
            <FileText {...iconProps} className="text-ink-muted" />
            <div className="min-w-0 flex-1">
              <p className="figure truncate text-sm">{value.kind === "sample" ? value.file : value.name}</p>
              <p className="text-xs text-ink-muted">
                {value.kind === "sample" ? `Our sample: hides an instruction using ${value.label.toLowerCase()}` : `${(value.size / 1024).toFixed(0)} KB, your file`}
              </p>
            </div>
            {allowUpload && (
              <Button variant="ghost" size="sm" onClick={() => input.current?.click()}>
                Replace
              </Button>
            )}
            <Button variant="ghost" size="icon-sm" aria-label="Remove the PDF" onClick={() => onChange(null)}>
              <X {...iconProps} />
            </Button>
          </div>
        ) : !allowUpload ? (
          <p className="text-sm text-ink-muted">No PDF attached.</p>
        ) : (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            <Upload {...iconProps} className="text-ink-muted" />
            <span className="text-sm">Drop an invoice PDF here, or</span>
            <Button size="sm" onClick={() => input.current?.click()}>
              Choose a PDF
            </Button>
            <span className="text-xs text-ink-muted">Up to 5 MB</span>
          </div>
        )}
        {allowUpload && (
          <input
            ref={input}
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            aria-label="Invoice PDF"
            onChange={(e) => {
              void take(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        )}
      </div>
      {error && <p className="mt-1.5 text-sm">{error}</p>}
      {!allowUpload && <p className="mt-1.5 text-sm text-ink-muted">Custom PDFs are scanned when the live backend is connected.</p>}
      {value?.kind !== "sample" && (
        <Button variant="link" size="sm" className="mt-2" onClick={() => onChange({ kind: "sample", file: sample.file, label: sample.label })}>
          Use our sample poisoned invoice
        </Button>
      )}
    </div>
  );
}
