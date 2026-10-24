"""From the phone evidence found on a site to one dataset row: primary_phone, agreement and confidence."""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from .crawl import CrawlResult
from .phones import Evidence, is_contact_url

AGREEMENT = ("consistent", "conflicting", "none_found")
CONFIDENCE = ("high", "medium", "low")

_NAMES = {"tel_link": "tel link", "json_ld": "JSON-LD", "contact_page_text": "contact page text", "footer_text": "footer text", "other_text": "other text"}


def group(evidence: list[Evidence]) -> list[dict]:
    """The numbers found, best first. A source is one (source_url, found_in) pair, so the same number in the JSON-LD and in the
    footer of one page is two sources. Ranking: most sources, then a JSON-LD source, then a contact page source."""
    by_phone: dict[str, list[Evidence]] = defaultdict(list)
    for item in evidence:
        by_phone[item.phone].append(item)

    def rank(phone: str) -> tuple:
        items = by_phone[phone]
        return (-len(items), not any(i.found_in == "json_ld" for i in items),
                not any(i.found_in == "contact_page_text" or is_contact_url(i.source_url) for i in items), phone)

    return [{"phone": p, "sources": [{"source_url": i.source_url, "found_in": i.found_in} for i in by_phone[p]]} for p in sorted(by_phone, key=rank)]


def assess(phones: list[dict], crawl: CrawlResult) -> tuple[Optional[str], str, str, str]:
    """(primary_phone, agreement, confidence, confidence_reason)."""
    if not phones:
        if not crawl.site_reachable:
            return None, "none_found", "low", "The website could not be reached."
        if crawl.pages_crawled == 0:
            return None, "none_found", "low", "robots.txt does not allow crawling this website."
        return None, "none_found", "low", f"No phone number found on {crawl.pages_crawled} page(s)."
    primary = phones[0]["phone"]
    if len(phones) > 1:
        listed = ", ".join(f"{p['phone']} ({len(p['sources'])} source{'' if len(p['sources']) == 1 else 's'})" for p in phones)
        return primary, "conflicting", "low", f"{len(phones)} different numbers found: {listed}. Do not call until a person has checked."
    types = sorted({s["found_in"] for s in phones[0]["sources"]})
    pages = len({s["source_url"] for s in phones[0]["sources"]})
    named = ", ".join(_NAMES[t] for t in types)
    if len(types) >= 2:
        return primary, "consistent", "high", f"One number, found in {len(types)} source types ({named}) on {pages} page(s)."
    return primary, "consistent", "medium", f"One number, found in only one source type ({named}) on {pages} page(s)."


def build_row(name: str, website_url: str, crawl: CrawlResult) -> dict:
    phones = group(crawl.evidence)
    primary, agreement, confidence, reason = assess(phones, crawl)
    return {
        "name": name,
        "website_url": website_url,
        "primary_phone": primary,
        "phones": phones,
        "agreement": agreement,
        "confidence": confidence,
        "confidence_reason": reason,
        "site_reachable": crawl.site_reachable,
        "final_url": crawl.final_url,
        "pages_crawled": crawl.pages_crawled,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def failed_row(name: str, website_url: str, reason: str) -> dict:
    """A business that could not be checked at all (bad input, or an unexpected error): still one row, never a failed run."""
    return {
        "name": name, "website_url": website_url, "primary_phone": None, "phones": [], "agreement": "none_found", "confidence": "low",
        "confidence_reason": reason, "site_reachable": False, "final_url": None, "pages_crawled": 0,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
