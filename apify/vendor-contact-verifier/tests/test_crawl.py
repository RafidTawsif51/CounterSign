"""The crawler against local fixtures served over real HTTP. No internet."""

import pytest

from src.assess import build_row
from src.crawl import crawl_site

PATHS = ["/contact", "/contact-us", "/about"]


async def check(url, **kw):
    kw.setdefault("max_pages", 10)
    kw.setdefault("extra_paths", PATHS)
    kw.setdefault("timeout", 5)
    return build_row("Vendor", url, await crawl_site(url, **kw))


async def test_consistent_site(site):
    row = await check(f"{site['site']}/consistent/")
    assert row["agreement"] == "consistent" and row["confidence"] == "high" and row["primary_phone"] == "+14155550101"
    kinds = {s["found_in"] for s in row["phones"][0]["sources"]}
    assert {"tel_link", "json_ld", "footer_text", "contact_page_text"} <= kinds
    assert row["site_reachable"] is True and row["pages_crawled"] == 2 and row["final_url"] == f"{site['site']}/consistent/"
    assert all(s["source_url"].startswith(site["site"]) for s in row["phones"][0]["sources"])


async def test_conflicting_site(site):
    row = await check(f"{site['site']}/conflicting/")
    assert row["agreement"] == "conflicting" and row["confidence"] == "low"
    assert {p["phone"] for p in row["phones"]} == {"+14155550102", "+14155550177"}
    by = {p["phone"]: {s["source_url"].rsplit("/", 1)[-1] for s in p["sources"]} for p in row["phones"]}
    assert by["+14155550177"] == {"contact.html"} and "index.html" in by["+14155550102"] or "" in by["+14155550102"]


async def test_none_found_ignores_hidden_script_form_comment_and_bare_digits(site):
    row = await check(f"{site['site']}/none_found/")
    assert (row["agreement"], row["confidence"], row["primary_phone"], row["phones"]) == ("none_found", "low", None, [])
    assert row["site_reachable"] is True and row["pages_crawled"] == 2 and "No phone number found" in row["confidence_reason"]


async def test_json_ld_only(site):
    row = await check(f"{site['site']}/jsonld_only/")
    assert row["primary_phone"] == "+14155550103" and [s["found_in"] for s in row["phones"][0]["sources"]] == ["json_ld"]
    assert (row["agreement"], row["confidence"]) == ("consistent", "medium")


async def test_tel_link_only(site):
    row = await check(f"{site['site']}/tel_only/")
    assert row["primary_phone"] == "+14155550104" and [s["found_in"] for s in row["phones"][0]["sources"]] == ["tel_link"]
    assert (row["agreement"], row["confidence"]) == ("consistent", "medium")


async def test_unreachable_site_gives_a_row_not_an_error():
    row = await check("http://127.0.0.1:1/", timeout=2)  # nothing listens on port 1
    assert row["site_reachable"] is False and row["pages_crawled"] == 0 and row["final_url"] is None
    assert (row["agreement"], row["confidence"], row["primary_phone"]) == ("none_found", "low", None)
    assert "could not be reached" in row["confidence_reason"]


async def test_a_link_to_another_host_is_never_followed(site):
    row = await check(f"{site['site']}/cross_host/")
    assert site["other_hits"] == []  # the other host got no request at all
    assert row["primary_phone"] == "+14155550105" and row["agreement"] == "consistent"
    assert "+14155550199" not in str(row)
    assert all(s["source_url"].startswith(site["site"]) for p in row["phones"] for s in p["sources"])


async def test_a_redirect_to_another_host_is_not_followed(site):
    row = await check(f"{site['site']}/redirect_other_host/index.html", extra_paths=[])
    assert site["other_hits"] == [] and row["pages_crawled"] == 0 and row["site_reachable"] is False and row["phones"] == []


async def test_a_redirect_inside_the_host_is_followed_and_final_url_says_where(site):
    row = await check(f"{site['site']}/redirect_same_host/index.html", extra_paths=[])
    assert row["final_url"] == f"{site['site']}/consistent/index.html" and row["primary_phone"] == "+14155550101"


async def test_robots_txt_that_disallows_everything_stops_the_crawl(host):
    url, hits = host("root_blocked")
    row = await check(url + "/")
    assert row["pages_crawled"] == 0 and row["phones"] == [] and "robots.txt" in row["confidence_reason"]
    assert hits == ["/robots.txt"]  # only robots.txt was requested: no page was fetched


async def test_robots_txt_that_disallows_one_page_skips_only_that_page(host):
    url, hits = host("root_partial")
    row = await check(url + "/")
    assert {p["phone"] for p in row["phones"]} == {"+14155550107"}  # the homepage was read, contact.html (0108) was not
    assert "/contact.html" not in hits and "/" in hits


async def test_a_server_error_on_robots_txt_means_nothing_is_allowed(host, monkeypatch):
    url, hits = host("consistent")  # no robots.txt here, so make it a 500 by pointing the crawler at a failing answer
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(request.url.path)
        return httpx.Response(500) if request.url.path == "/robots.txt" else httpx.Response(200, text="<p>(415) 555-0100</p>", headers={"content-type": "text/html"})

    from src.crawl import crawl_site

    result = await crawl_site("https://vendor.test/", max_pages=3, extra_paths=[], timeout=2, transport=httpx.MockTransport(handler))
    assert result.pages_crawled == 0 and result.evidence == [] and hits == ["/robots.txt"]


async def test_max_pages_per_site_limits_requests_including_failed_ones(site):
    row = await check(f"{site['site']}/many_pages/", max_pages=3, extra_paths=[])
    requested = [h for h in site["site_hits"] if "many_pages" in h]  # robots.txt is read at the host root and is not a page
    assert len(requested) == 3 and 1 <= row["pages_crawled"] <= 3  # one of them is the missing contact.html: a 404 still costs a request


async def test_extra_paths_resolve_inside_a_site_hosted_under_a_path(site):
    row = await check(f"{site['site']}/under_path/ivy/", extra_paths=["/contact.html"])
    assert row["primary_phone"] == "+14155550110" and row["pages_crawled"] == 2
    assert not any(h == "/contact.html" for h in site["site_hits"])  # not the host root


async def test_only_the_websites_host_is_ever_requested(site):
    await check(f"{site['site']}/cross_host/")
    assert site["other_hits"] == []
