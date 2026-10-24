# Owner: Aditya
# Prize track: Microsoft (Built for the Real World), Armadin
# Contract: features(pdf_bytes) -> dict[str, str]          one short hash per layout group
#           fingerprint(pdf_bytes) -> str                  one hash of all groups
#           layout_changed(pdf_bytes, past_fingerprints) -> bool
#           changed_groups(features, past_features) -> list[str]   which groups differ from the closest past layout
#   Feeds the "invoice format changed" signal in risk.py (weight 10).
#   The groups describe how a vendor draws its invoice, not what it says:
#     page     page size
#     fonts    the set of fonts used
#     logo     the first line's font, size and position
#     labels   where each "Label:" line sits and in what font
#     columns  the x positions of the table's column headings
#     table    the table's column heading words
#     footer   the last line's wording (digits ignored), position and size
#   Digits and amounts are ignored, so every invoice from the same vendor layout has the same fingerprint.
#   Hidden text (white, tiny, off-page, zero-width) never changes it.
#   A vendor with no past layouts is never reported as changed (nothing to compare).
# No flag: this is local and deterministic; it has no sponsor API.

import hashlib
import io
import re

_ZERO_WIDTH = set("​‌‍‎‏⁠﻿")
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


def _h(obj) -> str:
    return hashlib.sha256(repr(obj).encode()).hexdigest()[:8]


def _word_starts(chars: list) -> list[int]:
    """x position (to the nearest 10 pt) of every word in a line."""
    xs, prev_space = [], True
    for c in chars:
        if c["text"].isspace():
            prev_space = True
            continue
        if prev_space:
            xs.append(round(c["x0"] / 10))
        prev_space = False
    return xs


def features(pdf_bytes: bytes) -> dict[str, str]:
    (w, h), lines = _lines(pdf_bytes)

    # Hidden text must not change the layout: ignore white, tiny and off-page characters.
    def visible(line):
        return [c for c in line["chars"] if c["size"] >= 2 and c["x1"] <= w and c["x0"] >= 0 and c["top"] >= 0 and c["bottom"] <= h
                and not _is_white(c.get("non_stroking_color")) and c["text"] not in _ZERO_WIDTH]

    rows = [(ln, visible(ln)) for ln in lines]
    rows = [(ln, ch) for ln, ch in rows if ch and "".join(c["text"] for c in ch).strip()]
    fonts = sorted({c["fontname"].split("+")[-1] for _ln, ch in rows for c in ch})
    out = {"page": f"{w}x{h}", "fonts": _h(fonts)}
    if rows:
        first = rows[0][1][0]
        out["logo"] = _h((first["fontname"], round(first["size"]), round(rows[0][0]["x0"] / 10)))
    labels, header_text, columns = [], "", []
    for i, (ln, ch) in enumerate(rows):
        text = "".join(c["text"] for c in ch)
        m = _LABEL_RE.match(text)
        if m and "$" not in text.split(":")[0]:
            labels.append((m.group(1).strip().lower(), round(ln["x0"] / 10), ch[0]["fontname"], round(ch[0]["size"])))
        if not header_text and re.match(r"^1\.", text.strip()) and i > 0:
            prev = rows[i - 1][1]
            header_text = re.sub(r"[\d$.,]", "", "".join(c["text"] for c in prev)).strip()
            columns = _word_starts(prev)
    out["labels"], out["table"], out["columns"] = _h(labels), _h(header_text), _h(columns)
    if rows:
        last_ln, last_ch = rows[-1]
        out["footer"] = _h((re.sub(r"\d", "", "".join(c["text"] for c in last_ch)).strip(), round(last_ln["x0"] / 10), round(last_ch[0]["size"])))
    return out


def fingerprint(pdf_bytes: bytes) -> str:
    return hashlib.sha256(repr(sorted(features(pdf_bytes).items())).encode()).hexdigest()[:16]


def layout_changed(pdf_bytes: bytes, past_fingerprints: set[str] | list[str]) -> bool:
    if not past_fingerprints:
        return False
    return fingerprint(pdf_bytes) not in set(past_fingerprints)


def changed_groups(current: dict[str, str], past: list[dict[str, str]]) -> list[str]:
    """Groups that differ from the CLOSEST past layout (fewest differences). Empty if it matches one or there is none."""
    if not past:
        return []
    best = None
    for old in past:
        diff = sorted(g for g in set(current) | set(old) if current.get(g) != old.get(g))
        if not diff:
            return []
        if best is None or len(diff) < len(best):
            best = diff
    return best or []
