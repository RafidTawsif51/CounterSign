"""Pre-extract and pre-classify the seed so the demo run never waits on Claude for known documents.

    cd backend && python -m scripts.warm_cache [DIR]      # DIR defaults to seed/invoices

For every PDF in DIR: extract it (fills the extraction cache) and, when the real scanner is on, scan it
(fills the injection classifier cache). Then, if the database is seeded, scan the emails of this week's open
invoices (injection classifier and, with the real risk assessor, the urgency classifier). Five documents are processed at a time.

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
from app.services.risk import RealRiskAssessor, pressure_classifier  # noqa: E402

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
            msgs = s.exec(select(Message).join(Invoice, Invoice.message_id == Message.id).where(~Invoice.id.in_(select(Payment.invoice_id)))).all()
            s.expunge_all()
            return msgs
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
            assessor = RealRiskAssessor()

            def warm(m):
                injection.scan(ScanItem(kind="email", text=m.body, message_id=m.id))  # injection classifier
                if not settings.mock_risk:
                    assessor.pressure_detail(m)  # urgency classifier

            with ThreadPoolExecutor(WORKERS) as pool:
                list(pool.map(warm, msgs))
            print(f"Emails: classified {len(msgs)} messages behind the open invoices")
        print(f"Injection classifier: {injection.classifier.calls} live calls, {injection.classifier.errors} errors")
        print(f"Urgency classifier: {pressure_classifier.calls} live calls, {pressure_classifier.errors} errors")
    _warm_contacts(settings)
    print(f"Done in {time.perf_counter() - started:.1f}s")
    return 0 if failed == 0 else 2


def _warm_contacts(settings) -> None:
    """Run the independent phone lookup (our Vendor Contact Verifier Actor on Apify) for the demo vendor, so the first demo call starts fast.
    The result is cached for one hour (app/services/contacts.py), so run this shortly before the demo; the server also does it at start."""
    import asyncio

    from app.services import contacts

    if settings.mock_apify:
        print("MOCK_APIFY is true: the independent contact lookup is mocked, nothing to warm.")
        return
    t = time.perf_counter()
    result = asyncio.run(contacts.warm())
    print(f"Independent contact lookup (Apify): {result} in {time.perf_counter() - t:.1f}s, cached for {contacts.CACHE_TTL_SECONDS // 60} minutes in {settings.contacts_cache_dir}")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
