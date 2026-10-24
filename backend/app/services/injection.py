# Owner: Aditya
# Prize track: Armadin (Best Security Hack), Atlassian (Best Security Solution for Agents)
# Contract: scan(item: ScanItem) -> list[Finding]
#   Synchronous (call it with asyncio.to_thread). Pure: it writes nothing; use save_findings() to
#   store results. Never raises on hostile input. An empty list means nothing was found.
#   Finding.evidence_id is the id of the injection_findings row (save_findings stores it under that
#   id), so /ask can cite it.
# Flag: MOCK_INJECTION (separate from MOCK_CLAUDE, which only covers extraction). Layer 2, the
#   instruction classifier, is the Claude part; layer 1 is local.
# The mock runs a simplified layer 1 (hidden content) and a keyword layer 2. The real version adds
# the Claude Haiku classifier.

import io
import re
from dataclasses import dataclass
from typing import Literal, Optional, Protocol

from pydantic import BaseModel, Field
from sqlmodel import Session

from app.config import get_settings
from app.models import InjectionFinding, new_id


@dataclass
class ScanItem:
    kind: Literal["pdf", "email"]
    pdf_bytes: Optional[bytes] = None
    text: Optional[str] = None  # email body, plain or HTML
    invoice_id: Optional[str] = None
    message_id: Optional[str] = None


class Finding(BaseModel):
    technique: str  # white_text, tiny_font, off_page, zero_width, html_comment, hidden_element, instruction_text
    snippet: str
    confidence: float  # 0 to 1
    evidence_id: str = Field(default_factory=lambda: new_id("inj"))
    invoice_id: Optional[str] = None
    message_id: Optional[str] = None


class Scanner(Protocol):
    def scan(self, item: ScanItem) -> list[Finding]: ...


INSTRUCTION_PATTERNS = [
    r"ignore (?:all |any )?(?:previous|prior|above) (?:instructions|rules)",
    r"\bai assistant\b",
    r"\bassistant\s*:",
    r"\bsystem prompt\b",
    r"disregard (?:the |all )?(?:above|previous|rules)",
    r"update (?:the )?(?:remittance|bank|payment) (?:details|account|info)",
    r"change (?:the )?(?:bank|account|remittance)",
    r"\bapprove (?:this |the )?(?:payment|invoice)\b",
    r"\bdo not (?:flag|verify|call)\b",
]
_INSTRUCTION_RE = re.compile("|".join(INSTRUCTION_PATTERNS), re.I)
_ZERO_WIDTH_RE = re.compile("[​-‏⁠﻿‪-‮]+")
_HTML_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)
_HIDDEN_STYLE = r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|opacity\s*:\s*0|color\s*:\s*(?:#fff(?:fff)?|white)\b"
_HIDDEN_EL_RE = re.compile(rf"<(\w+)[^>]*style\s*=\s*[\"'][^\"']*(?:{_HIDDEN_STYLE})[^\"']*[\"'][^>]*>(.*?)</\1>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")

HIDDEN_WITH_INSTRUCTION = 0.95
HIDDEN_ONLY = 0.5
VISIBLE_INSTRUCTION = 0.7


def _clip(s: str, n: int = 200) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 3] + "..."


def _is_white(color) -> bool:
    if color is None:
        return False
    vals = color if isinstance(color, (tuple, list)) else (color,)
    if len(vals) == 4:  # CMYK: all zero is white
        return all(v <= 0.05 for v in vals)
    return len(vals) > 0 and all(v >= 0.95 for v in vals)


def _hidden_finding(technique: str, text: str) -> Finding:
    conf = HIDDEN_WITH_INSTRUCTION if _INSTRUCTION_RE.search(text) else HIDDEN_ONLY
    return Finding(technique=technique, snippet=_clip(text), confidence=conf)


class MockScanner:
    def scan(self, item: ScanItem) -> list[Finding]:
        try:
            findings = self._pdf(item) if item.kind == "pdf" else self._email(item)
        except Exception:  # hostile input must not crash the run
            findings = []
        for f in findings:
            f.invoice_id, f.message_id = item.invoice_id, item.message_id
        return findings

    def _text_findings(self, text: str, already_hidden: bool) -> list[Finding]:
        out: list[Finding] = []
        for m in _ZERO_WIDTH_RE.finditer(text):
            out.append(Finding(technique="zero_width", snippet=f"{len(m.group())} zero-width characters", confidence=0.8))
            break
        if not already_hidden:
            m = _INSTRUCTION_RE.search(text)
            if m:
                out.append(Finding(technique="instruction_text", snippet=_clip(text[max(0, m.start() - 40): m.end() + 80]), confidence=VISIBLE_INSTRUCTION))
        return out

    def _pdf(self, item: ScanItem) -> list[Finding]:
        import pdfplumber

        hidden: dict[str, list[str]] = {"white_text": [], "tiny_font": [], "off_page": []}
        all_text: list[str] = []
        with pdfplumber.open(io.BytesIO(item.pdf_bytes or b"")) as pdf:
            for page in pdf.pages:
                all_text.append(page.extract_text() or "")
                for ch in page.chars:
                    if ch["x0"] < 0 or ch["x1"] > page.width or ch["top"] < 0 or ch["bottom"] > page.height:
                        hidden["off_page"].append(ch["text"])
                    elif ch["size"] < 2:
                        hidden["tiny_font"].append(ch["text"])
                    elif _is_white(ch.get("non_stroking_color")):
                        hidden["white_text"].append(ch["text"])
        findings = [_hidden_finding(t, "".join(chars)) for t, chars in hidden.items() if "".join(chars).strip()]
        return findings + self._text_findings("\n".join(all_text), already_hidden=bool(findings))

    def _email(self, item: ScanItem) -> list[Finding]:
        body = item.text or ""
        findings = [_hidden_finding("html_comment", m.group(1)) for m in _HTML_COMMENT_RE.finditer(body) if m.group(1).strip()]
        for m in _HIDDEN_EL_RE.finditer(body):
            inner = _TAG_RE.sub(" ", m.group(2))
            if inner.strip():
                findings.append(_hidden_finding("hidden_element", inner))
        return findings + self._text_findings(_TAG_RE.sub(" ", body), already_hidden=bool(findings))


class RealScanner:
    """Layer 1 with full coverage plus the Claude Haiku yes/no instruction classifier. Aditya builds this."""

    def scan(self, item: ScanItem) -> list[Finding]:
        raise NotImplementedError("Real injection scanner is not built yet; set MOCK_INJECTION=true")


def get_scanner() -> Scanner:
    return MockScanner() if get_settings().mock_injection else RealScanner()


def scan(item: ScanItem) -> list[Finding]:
    return get_scanner().scan(item)


def save_findings(session: Session, findings: list[Finding]) -> None:
    """Store findings in injection_findings under their evidence_id. The caller commits."""
    for f in findings:
        session.add(
            InjectionFinding(
                id=f.evidence_id,
                invoice_id=f.invoice_id,
                message_id=f.message_id,
                technique=f.technique,
                snippet=f.snippet,
                confidence=f.confidence,
            )
        )
