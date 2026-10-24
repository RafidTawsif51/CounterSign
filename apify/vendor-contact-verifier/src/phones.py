"""Pull phone numbers out of one HTML page, with where on the page each one was found.

Sources, in the words the dataset uses (`found_in`):

    tel_link            a tel: link
    json_ld             a schema.org Organization or LocalBusiness block (telephone, contactPoint)
    contact_page_text   visible text on a page that is a contact page (its URL or heading says contact)
    footer_text         visible text inside a page footer
    other_text          any other visible text

Ignored: anything inside scripts and styles (except JSON-LD), forms, hidden elements and comments. Every number is normalized
to E.164 with the phonenumbers library, so (415) 555-0100 and +1 415-555-0100 are one number.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Optional
from urllib.parse import unquote, urldefrag, urlparse

import phonenumbers
from bs4 import BeautifulSoup, Comment, Tag
from phonenumbers import Leniency, PhoneNumberFormat, PhoneNumberMatcher, ValidationResult

DEFAULT_REGION = "US"  # numbers written without a country code are read as US/Canada numbers

FOUND_IN = ("tel_link", "json_ld", "contact_page_text", "footer_text", "other_text")

# schema.org types whose telephone counts. Organization and LocalBusiness and their common subtypes.
ORGANIZATION_TYPES = {
    "Organization", "LocalBusiness", "Corporation", "ProfessionalService", "HomeAndConstructionBusiness", "GeneralContractor",
    "Store", "AutomotiveBusiness", "FoodEstablishment", "MedicalBusiness", "FinancialService", "LegalService", "Electrician",
    "Plumber", "RoofingContractor", "HVACBusiness", "MovingCompany", "HousePainter",
}

_SKIP_TAGS = {"script", "style", "noscript", "template", "form", "head", "svg", "iframe", "select", "textarea", "option", "canvas"}
_HIDDEN_STYLE = re.compile(r"(display\s*:\s*none|visibility\s*:\s*hidden)", re.I)
_FOOTER_NAME = re.compile(r"footer", re.I)
_CONTACT_PATH = re.compile(r"contact", re.I)
_SEPARATED = re.compile(r"^\+|\d[\s().\-\u2013\u2014]+\d")  # a written number has a plus or separators, not a bare digit run


@dataclass(frozen=True)
class Evidence:
    phone: str  # E.164
    source_url: str
    found_in: str


@dataclass
class PageResult:
    evidence: list[Evidence]
    links: list[tuple[str, str]]  # (absolute href, link text) of every visible link, for the crawler


def normalize(raw: str, region: str = DEFAULT_REGION) -> Optional[str]:
    """E.164 for a phone written any common way, or None if it cannot be a phone number."""
    try:
        number = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return None
    # IS_POSSIBLE only: a 7-digit local number such as 555-0100 has no area code and is not enough to dial.
    # The number need not be assigned: the fictional 555 numbers of the demo are possible but not valid.
    if phonenumbers.is_possible_number_with_reason(number) != ValidationResult.IS_POSSIBLE:
        return None
    return phonenumbers.format_number(number, PhoneNumberFormat.E164)


def is_contact_url(url: str) -> bool:
    return bool(_CONTACT_PATH.search(urlparse(url).path))


def _is_hidden(tag: Tag) -> bool:
    if tag.attrs is None:
        return False
    attrs = tag.attrs
    if "hidden" in attrs or str(attrs.get("aria-hidden", "")).lower() == "true":
        return True
    if tag.name == "input" and str(attrs.get("type", "")).lower() == "hidden":
        return True
    return bool(_HIDDEN_STYLE.search(str(attrs.get("style", ""))))


def _is_footer(tag: Tag) -> bool:
    if tag.name == "footer" or str(tag.attrs.get("role", "")).lower() == "contentinfo":
        return True
    ident = " ".join([str(tag.attrs.get("id", "")), " ".join(tag.attrs.get("class", []) or [])])
    return bool(_FOOTER_NAME.search(ident)) and tag.name in {"div", "section", "aside", "nav"}


def _walk_json(node: Any) -> Iterator[dict]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_json(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_json(item)


def _types(node: dict) -> set[str]:
    t = node.get("@type")
    values = t if isinstance(t, list) else [t]
    return {str(v).rsplit("/", 1)[-1] for v in values if v}


def _json_ld_numbers(soup: BeautifulSoup) -> list[str]:
    out: list[str] = []
    for script in soup.find_all("script"):
        if str(script.get("type", "")).lower().split(";")[0].strip() != "application/ld+json":
            continue
        try:
            data = json.loads(script.string or script.get_text() or "")
        except ValueError:
            continue
        for node in _walk_json(data):
            if not _types(node) & ORGANIZATION_TYPES:
                continue
            candidates: list[Any] = [node.get("telephone")]
            contact = node.get("contactPoint")
            for point in contact if isinstance(contact, list) else [contact]:
                if isinstance(point, dict):
                    candidates.append(point.get("telephone"))
            for value in candidates:
                for item in value if isinstance(value, list) else [value]:
                    if isinstance(item, str) and (e164 := normalize(item)):
                        out.append(e164)
    return out


def _text_numbers(text: str) -> Iterable[str]:
    for match in PhoneNumberMatcher(text, DEFAULT_REGION, leniency=Leniency.POSSIBLE):
        if not _SEPARATED.search(match.raw_string.strip()):
            continue
        if (e164 := normalize(match.raw_string)) is not None:
            yield e164


def extract_page(html: str, page_url: str) -> PageResult:
    """All phone evidence on one page, and its visible links."""
    from urllib.parse import urljoin

    soup = BeautifulSoup(html, "html.parser")
    evidence: list[Evidence] = []

    def add(phone: str, found_in: str) -> None:
        item = Evidence(phone, page_url, found_in)
        if item not in evidence:
            evidence.append(item)

    for phone in _json_ld_numbers(soup):  # before scripts are removed
        add(phone, "json_ld")

    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    for tag in soup.find_all(_SKIP_TAGS):
        tag.decompose()
    for tag in soup.find_all(True):
        if not tag.decomposed and _is_hidden(tag):
            tag.decompose()

    links: list[tuple[str, str]] = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"]).strip()
        if href.lower().startswith("tel:"):
            if e164 := normalize(unquote(href[4:]).split(";")[0]):
                add(e164, "tel_link")
        elif not re.match(r"^(mailto|javascript|sms|data):", href, re.I):
            links.append((urldefrag(urljoin(page_url, href))[0], a.get_text(" ", strip=True)))

    h1 = soup.find("h1")
    contact_page = is_contact_url(page_url) or bool(h1 and _CONTACT_PATH.search(h1.get_text(" ", strip=True)))

    footers = [t for t in soup.find_all(_is_footer) if not any(_is_footer(p) for p in t.parents if isinstance(p, Tag))]
    for footer in footers:
        for phone in _text_numbers(footer.get_text(" ", strip=True)):
            add(phone, "footer_text")
        footer.decompose()
    for phone in _text_numbers(soup.get_text(" ", strip=True)):
        add(phone, "contact_page_text" if contact_page else "other_text")

    return PageResult(evidence, links)
