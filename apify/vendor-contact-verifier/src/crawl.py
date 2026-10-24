"""Crawl one website: its homepage and a few more pages, inside the website's own folder only.

Rules that matter for a payment-fraud check:
  * Only URLs on the host of website_url AND under its path prefix are ever requested. For https://host/org/acme/ that is
    /org/acme/; for a site at a domain root the prefix is / and every page of the host is in scope. Many vendors can share one
    host (GitHub Pages, a marketplace), so a link to a neighbour's folder, to another host, or a redirect to either is not
    followed. (example.com and www.example.com count as the same host.)
  * robots.txt is read first and obeyed (RFC 9309: a missing file allows everything, a 5xx answer allows nothing).
  * Only public pages are fetched, as a plain HTTP client: no cookies, no logins, no JavaScript.
"""

import posixpath
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Optional
from typing import Callable
from urllib.parse import unquote, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import httpx

from .phones import Evidence, extract_page

USER_AGENT = "VendorContactVerifier/1.0 (Apify Actor; reads public contact pages only)"
ROBOTS_TOKEN = "VendorContactVerifier"
MAX_REDIRECTS = 5
MAX_BYTES = 2_000_000
_SKIP_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|webp|svg|ico|zip|gz|mp4|mp3|css|js|xml|json|docx?|xlsx?)$", re.I)
_CONTACT_HINT = re.compile(r"contact|about|call|reach|phone", re.I)


def site_key(url: str) -> str:
    """The host a crawl is limited to: lowercase host and port, without a leading www."""
    p = urlparse(url)
    host = (p.hostname or "").lower().removeprefix("www.")
    default = {"http": 80, "https": 443}.get(p.scheme)
    return f"{host}:{p.port or default}"


def normal_path(path: str) -> str:
    """The path a server will serve for a URL path: percent-escapes decoded (%2e%2e is ..), backslashes and repeated slashes
    collapsed, . and .. resolved. Scope is decided on this, so ../neighbour/ cannot slip out of the folder."""
    decoded = re.sub(r"/+", "/", unquote(path).replace("\\", "/"))
    trailing = decoded.endswith("/")
    resolved = posixpath.normpath("/" + decoded.lstrip("/"))  # normpath keeps a leading //, so strip first
    return resolved + ("/" if trailing and resolved != "/" else "")


class Scope:
    """What one crawl may request: the host of website_url, under the folder website_url is in."""

    def __init__(self, website_url: str, prefix: str) -> None:
        self.host = site_key(website_url)
        self.prefix = normal_path(prefix if prefix.endswith("/") else prefix + "/")

    def same_host(self, url: str) -> bool:
        return urlparse(url).scheme in ("http", "https") and site_key(url) == self.host

    def contains(self, url: str) -> bool:
        if not self.same_host(url):
            return False
        path = normal_path(urlparse(url).path or "/")
        return (path if path.endswith("/") else path + "/").startswith(self.prefix)


def clean_url(url: str) -> str:
    p = urlparse(url)
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path or "/", p.params, p.query, ""))


def page_key(url: str) -> str:
    """Identity of a page for "already fetched". /dir/ and /dir/index.html are one page, and so are /contact and /contact.html
    (GitHub Pages and many servers answer both with the same file)."""
    p = urlparse(clean_url(url))
    path = re.sub(r"\.html?$", "", re.sub(r"/index\.html?$", "/", p.path))
    return urlunparse((p.scheme, p.netloc, path, p.params, p.query, ""))


@dataclass
class Fetched:
    url: str  # the URL that answered, after in-scope redirects
    status: Optional[int] = None
    html: Optional[str] = None  # set for a 2xx HTML page
    error: Optional[str] = None  # why nothing came back
    left_scope: bool = False  # a redirect led outside the allowed host and folder and was not followed


@dataclass
class CrawlResult:
    evidence: list[Evidence] = field(default_factory=list)
    pages_crawled: int = 0
    site_reachable: bool = False
    final_url: Optional[str] = None
    robots_blocked: int = 0  # URLs not fetched because robots.txt disallows them
    other_host_skipped: int = 0  # links and redirects to another host that were not followed
    outside_folder_skipped: int = 0  # same host, but outside the website_url folder: not followed
    notes: list[str] = field(default_factory=list)


class Client:
    """One HTTP client for one business: timeouts, a size cap, manual redirects that must stay in scope."""

    def __init__(self, timeout: float, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        self._http = httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}, transport=transport)

    async def close(self) -> None:
        await self._http.aclose()

    async def get(self, url: str, allowed: Callable[[str], bool], *, want_html: bool = True) -> Fetched:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            try:
                async with self._http.stream("GET", current) as r:
                    if r.is_redirect and r.headers.get("location"):
                        nxt = clean_url(urljoin(current, r.headers["location"]))
                        if not allowed(nxt):
                            return Fetched(current, r.status_code, error="redirect out of scope", left_scope=True)
                        current = nxt
                        continue
                    body = bytearray()
                    async for chunk in r.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            break
                    ctype = r.headers.get("content-type", "").lower()
                    if r.status_code >= 400:
                        return Fetched(current, r.status_code, error=f"HTTP {r.status_code}")
                    if want_html and ctype and "html" not in ctype:
                        return Fetched(current, r.status_code, error=f"not HTML ({ctype.split(';')[0]})")
                    return Fetched(current, r.status_code, html=bytes(body[:MAX_BYTES]).decode(r.encoding or "utf-8", errors="replace"))
            except httpx.TimeoutException:
                return Fetched(current, error="timeout")
            except httpx.InvalidURL:
                return Fetched(current, error="invalid URL")
            except httpx.HTTPError as exc:
                return Fetched(current, error=type(exc).__name__)
        return Fetched(current, error="too many redirects")


async def load_robots(client: Client, origin: str, scope: Scope) -> RobotFileParser:
    parser = RobotFileParser()
    got = await client.get(f"{origin}/robots.txt", scope.same_host, want_html=False)  # robots.txt lives at the host root
    if got.html is not None:
        parser.parse(got.html.splitlines())
    elif got.status is not None and got.status >= 500:
        parser.disallow_all = True  # RFC 9309: the file is unreachable because of a server error, assume nothing is allowed
    else:
        parser.allow_all = True  # no robots.txt (404, 403, or the host answered another way): no restrictions
    return parser


def _base(website_url: str) -> str:
    """The site's root folder: website_url as a directory, so that an extra path like /contact resolves inside it.
    A site hosted under a path (https://host/org/site/) keeps that path; a file name (index.html) is dropped."""
    u = clean_url(website_url)
    if u.endswith("/"):
        return u
    head, _, last = u.rpartition("/")
    return head + "/" if "." in last else u + "/"


async def crawl_site(website_url: str, *, max_pages: int, extra_paths: list[str], timeout: float, transport: Optional[httpx.AsyncBaseTransport] = None) -> CrawlResult:
    result = CrawlResult()
    parsed = urlparse(website_url)
    base = _base(website_url)
    scope = Scope(website_url, urlparse(base).path)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    client = Client(timeout, transport)
    try:
        robots = await load_robots(client, origin, scope)
        home = clean_url(website_url)
        queue: deque[str] = deque([home] + [clean_url(urljoin(base, p.lstrip("/"))) for p in extra_paths])
        seen: set[str] = set()
        attempts = 0
        first = True
        while queue and attempts < max_pages:
            url = queue.popleft()
            if page_key(url) in seen:
                continue
            seen.add(page_key(url))
            if not scope.contains(url):  # an extra path such as ../neighbour/ is checked like any link
                if scope.same_host(url):
                    result.outside_folder_skipped += 1
                else:
                    result.other_host_skipped += 1
                continue
            if not robots.can_fetch(ROBOTS_TOKEN, url):
                result.robots_blocked += 1
                continue
            attempts += 1
            got = await client.get(url, scope.contains)
            if first:
                first = False
                if got.html is not None:
                    result.final_url = got.url
            if got.left_scope:
                result.other_host_skipped += 1  # a redirect out of the folder or host: never requested
            if got.html is None:
                continue
            seen.add(page_key(got.url))
            result.pages_crawled += 1
            result.site_reachable = True
            page = extract_page(got.html, got.url)
            for item in page.evidence:
                if item not in result.evidence:
                    result.evidence.append(item)
            found: list[str] = []
            texts: dict[str, str] = {}
            for href, text in page.links:
                if not href.startswith(("http://", "https://")) or _SKIP_EXT.search(urlparse(href).path):
                    continue
                if not scope.contains(href):
                    if scope.same_host(href):
                        result.outside_folder_skipped += 1  # a neighbour's folder on the same host: never followed
                    else:
                        result.other_host_skipped += 1  # another host: never followed
                    continue
                link = clean_url(href)
                texts.setdefault(link, text)
                if page_key(link) not in seen and link not in queue and link not in found:
                    found.append(link)
            # Pages that look like contact pages are fetched first.
            hinted = [link for link in found if _CONTACT_HINT.search(link) or _CONTACT_HINT.search(texts.get(link, ""))]
            queue.extendleft(reversed(hinted))
            queue.extend(link for link in found if link not in hinted)
        if not result.site_reachable and attempts == 0 and result.robots_blocked:
            result.site_reachable = True  # robots.txt answered; the site is up but asks not to be crawled
            result.notes.append("robots.txt does not allow crawling")
    finally:
        await client.close()
    return result
