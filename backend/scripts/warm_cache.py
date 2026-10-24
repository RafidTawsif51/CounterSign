"""Pre-extract every seed invoice so the demo never waits on Claude for known documents.

    cd backend && python -m scripts.warm_cache [DIR]      # DIR defaults to seed/invoices

Needs MOCK_CLAUDE=false and a real key to fill the caches (extraction, and the injection classifier when MOCK_INJECTION=false); with mocks on it only previews the
mock output and writes nothing. Live runs spend API credits, once per new document.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.services.extract import ExtractionFailed, extract_pdf  # noqa: E402
from app.services import injection  # noqa: E402
from app.services.injection import ScanItem  # noqa: E402


def main(argv: list[str]) -> int:
    folder = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent / "seed" / "invoices"
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs in {folder}. Generate the seed invoices first.")
        return 1

    settings = get_settings()
    if settings.mock_claude:
        print("MOCK_CLAUDE is true: showing mock extractions, nothing is cached.\n")
    else:
        print(f"Live extraction with {settings.claude_model_main}; results are cached in {settings.extract_cache_dir}\n")

    ok = failed = 0
    print(f"{'file':<28} {'source':<7} {'vendor':<28} {'amount':>11}  remittance")
    for pdf in pdfs:
        try:
            ex = extract_pdf(pdf.read_bytes())
        except ExtractionFailed as exc:
            failed += 1
            print(f"{pdf.name:<28} {'-':<7} {'EXTRACTION FAILED':<28} {'':>11}  {exc.reason}")
            continue
        ok += 1
        if not settings.mock_claude and not settings.mock_injection:
            injection.scan(ScanItem(kind="pdf", pdf_bytes=pdf.read_bytes()))  # also fills the classifier cache
        rem = f"{ex.remittance.bank_name} ****{ex.remittance.account_last4}" if ex.remittance else "none"
        print(f"{pdf.name:<28} {ex.source:<7} {ex.vendor_name[:27]:<28} {ex.amount_usd:>11,.2f}  {rem}")
    print(f"\n{ok} extracted, {failed} failed, {len(pdfs)} total")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
