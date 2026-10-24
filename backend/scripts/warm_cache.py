"""Pre-extract and pre-classify the seed so the demo run never waits on Claude for known documents.

    cd backend && python -m scripts.warm_cache [DIR]      # DIR defaults to seed/invoices

For every PDF in DIR: extract it (fills the extraction cache) and, when the real scanner is on, scan it
(fills the injection classifier cache). Then, if the database is seeded, scan the emails of this week's open
invoices. Five documents are processed at a time.

Needs MOCK_CLAUDE=false and a real key to fill the caches; with mocks on it only previews the mock output and
writes nothing. Live runs spend API credits, once per new document.
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.services import injection  # noqa: E402
from app.services.extract import ExtractionFailed, extract_pdf  # noqa: E402
from app.services.injection import ScanItem  # noqa: E402

WORKERS = 5


def _pdf(pdf: Path, scan: bool):
    data = pdf.read_bytes()
    try:
        ex = extract_pdf(data)
    except ExtractionFailed as exc:
        return pdf, None, exc.reason
    if scan:
        injection.scan(ScanItem(kind="pdf", pdf_bytes=data))  # also fills the classifier cache
    return pdf, ex, None


def _open_invoice_messages():
    """Bodies of the emails behind this week's open invoices, if the database is seeded."""
    from app.db import engine
    from app.models import Invoice, Message, Payment

    try:
        with Session(engine) as s:
            rows = s.exec(select(Message.id, Message.body).join(Invoice, Invoice.message_id == Message.id).where(~Invoice.id.in_(select(Payment.invoice_id)))).all()
            return [(i, b) for i, b in rows]
    except Exception:
        return []


def main(argv: list[str]) -> int:
    folder = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "seed" / "invoices"
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs in {folder}. Generate the seed invoices first.")
        return 1

    settings = get_settings()
    live = not settings.mock_claude
    scan = live and not settings.mock_injection
    if not live:
        print("MOCK_CLAUDE is true: showing mock extractions, nothing is cached.\n")
    else:
        print(f"Live extraction with {settings.claude_model_main}; classifier {'on, ' + settings.claude_model_fast if scan else 'off'}; "
              f"caches in {settings.extract_cache_dir} and {settings.injection_cache_dir}\n")

    started = time.perf_counter()
    ok = failed = cached = 0
    print(f"{'file':28} {'source':7} {'vendor':28} {'amount':>11}  remittance")
    with ThreadPoolExecutor(WORKERS) as pool:
        for pdf, ex, err in pool.map(lambda p: _pdf(p, scan), pdfs):
            if ex is None:
                failed += 1
                print(f"{pdf.name:<28} {'-':<7} {'EXTRACTION FAILED':<28} {'':>11}  {err}")
                continue
            ok += 1
            cached += ex.source == "cache"
            rem = f"{ex.remittance.bank_name} ****{ex.remittance.account_last4}" if ex.remittance else "none"
            print(f"{pdf.name:<28} {ex.source:<7} {ex.vendor_name[:27]:<28} {ex.amount_usd:>11,.2f}  {rem}")
    print(f"\nPDFs: {ok} extracted ({cached} already cached), {failed} failed, {len(pdfs)} total")

    if scan:
        msgs = _open_invoice_messages()
        if msgs:
            with ThreadPoolExecutor(WORKERS) as pool:
                list(pool.map(lambda m: injection.scan(ScanItem(kind="email", text=m[1], message_id=m[0])), msgs))
            print(f"Emails: classified {len(msgs)} messages behind the open invoices")
        print(f"Classifier: {injection.classifier.calls} live calls, {injection.classifier.errors} errors")
    print(f"Done in {time.perf_counter() - started:.1f}s")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
