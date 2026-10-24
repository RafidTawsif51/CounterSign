# Owner: Aditya
# Prize track: Microsoft (Built for the Real World), Armadin
# Contract: fingerprint(pdf_bytes) -> str, layout_changed(pdf_bytes, past_fingerprints) -> bool
#   Feeds RiskContext.layout_changed (the "invoice format changed" signal, weight 10).
#   The fingerprint describes how a vendor draws its invoice, not what it says: fonts, sizes, page size,
#   where each "Label:" line sits, the table header row, and the footer. Digits and amounts are ignored,
#   so every invoice from the same vendor layout has the same fingerprint.
#   A vendor with no past fingerprints is never reported as changed (nothing to compare).
# No flag: this is local and deterministic; it has no sponsor API.

import hashlib
import io
import re

_ZERO_WIDTH = set("\u200b\u200c\u200d\u200e\u200f\u2060\ufeff")
_LABEL_RE = re.compile(r"^\s*([A-Za-z#][A-Za-z# .]{1,22}):")


def _is_white(color) -> bool:
    vals = color if isinstance(color, (tuple, list)) else (color,) if color is not None else ()
    if len(vals) == 4:
        return all(v <= 0.05 for v in vals)
    return bool(vals) and all(v >= 0.95 for v in vals)


def _lines(pdf_bytes: bytes):
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        return (round(page.width), round(page.height)), page.extract_text_lines(return_chars=True)


def fingerprint(pdf_bytes: bytes) -> str:
    (w, h), lines = _lines(pdf_bytes)
    # Hidden text must not change the fingerprint: ignore white, tiny and off-page characters.
    def visible(line):
        return [c for c in line["chars"] if c["size"] >= 2 and c["x1"] <= w and c["x0"] >= 0 and c["top"] >= 0 and c["bottom"] <= h
                and not _is_white(c.get("non_stroking_color")) and c["text"] not in _ZERO_WIDTH]

    feats: list = [("page", w, h)]
    rows = [(ln, visible(ln)) for ln in lines]
    rows = [(ln, ch) for ln, ch in rows if ch and "".join(c["text"] for c in ch).strip()]
    if rows:
        first = rows[0][1][0]
        feats.append(("logo", first["fontname"], round(first["size"]), round(rows[0][0]["x0"] / 10)))
    header = None
    for i, (ln, ch) in enumerate(rows):
        text = "".join(c["text"] for c in ch)
        m = _LABEL_RE.match(text)
        if m and "$" not in text.split(":")[0]:
            feats.append(("label", m.group(1).strip().lower(), round(ln["x0"] / 10), ch[0]["fontname"], round(ch[0]["size"])))
        if header is None and re.match(r"^1\.", text.strip()) and i > 0:
            header = re.sub(r"[\d$.,]", "", "".join(c["text"] for c in rows[i - 1][1])).strip()
            feats.append(("table", header, rows[i - 1][1][0]["fontname"]))
    if rows:
        last_ln, last_ch = rows[-1]
        feats.append(("footer", re.sub(r"\d", "", "".join(c["text"] for c in last_ch)).strip(), round(last_ln["x0"] / 10), round(last_ch[0]["size"])))
    return hashlib.sha256(repr(feats).encode()).hexdigest()[:16]


def layout_changed(pdf_bytes: bytes, past_fingerprints: set[str] | list[str]) -> bool:
    if not past_fingerprints:
        return False
    return fingerprint(pdf_bytes) not in set(past_fingerprints)
