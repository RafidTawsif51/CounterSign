"""Actor entry point: read the input, check each business on its own, write one dataset row per business."""

import asyncio
from typing import Any
from urllib.parse import urlparse

from apify import Actor

from .assess import build_row, failed_row
from .crawl import crawl_site

DEFAULT_EXTRA_PATHS = ["/contact", "/contact-us", "/about"]
MAX_PAGES_LIMIT = 30
CONCURRENCY = 5  # businesses checked at the same time; the pages of one site are fetched one after another


def validate(business: Any) -> tuple[str, str, str | None]:
    """(name, website_url, problem). problem is None for a usable business."""
    if not isinstance(business, dict):
        return "", "", "Each business must be an object with name and website_url."
    name = str(business.get("name") or "").strip()
    url = str(business.get("website_url") or "").strip()
    if not name:
        return name, url, "Missing name."
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return name, url, "website_url must be a full http:// or https:// URL."
    return name, url, None


def read_options(data: dict) -> tuple[int, list[str], float]:
    max_pages = int(data.get("maxPagesPerSite") or 10)
    paths = data.get("extraPaths")
    timeout = float(data.get("requestTimeoutSecs") or 15)
    return max(1, min(max_pages, MAX_PAGES_LIMIT)), [str(p) for p in (DEFAULT_EXTRA_PATHS if paths is None else paths)], max(1.0, timeout)


async def check_business(business: Any, max_pages: int, extra_paths: list[str], timeout: float) -> dict:
    name, url, problem = validate(business)
    if problem:
        return failed_row(name, url, f"Not checked: {problem}")
    try:
        crawl = await crawl_site(url, max_pages=max_pages, extra_paths=extra_paths, timeout=timeout)
        return build_row(name, url, crawl)
    except Exception as exc:  # one bad site must never fail the run
        Actor.log.exception("Check failed for %s", name)
        return failed_row(name, url, f"Check failed: {type(exc).__name__}.")


async def main() -> None:
    async with Actor:
        data = await Actor.get_input() or {}
        businesses = data.get("businesses")
        if not isinstance(businesses, list) or not businesses:
            await Actor.fail(status_message="Input needs a non-empty businesses array of {name, website_url}.")
            return
        max_pages, extra_paths, timeout = read_options(data)
        gate = asyncio.Semaphore(CONCURRENCY)

        async def one(i: int, business: Any) -> dict:
            async with gate:
                row = await check_business(business, max_pages, extra_paths, timeout)
            Actor.log.info(
                "[%d/%d] %s: %s, %s confidence, %s, %d page(s)",
                i + 1, len(businesses), row["name"] or "(no name)", row["agreement"], row["confidence"], row["primary_phone"] or "no phone", row["pages_crawled"],
            )
            return row

        rows = await asyncio.gather(*(one(i, b) for i, b in enumerate(businesses)))
        await Actor.push_data(list(rows))  # in input order
        await Actor.set_status_message(f"Checked {len(rows)} business(es).")
