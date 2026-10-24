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


async def test_a_redirect_inside_the_folder_is_followed_and_final_url_says_where(site):
    row = await check(f"{site['site']}/redirect_in_folder/index.html", extra_paths=[])
    assert row["final_url"] == f"{site['site']}/redirect_in_folder/target.html" and row["primary_phone"] == "+14155550211"


async def test_a_redirect_to_a_neighbours_folder_is_not_followed(site):
    row = await check(f"{site['site']}/redirect_out_of_folder/index.html", extra_paths=[])
    assert row["phones"] == [] and row["pages_crawled"] == 0 and row["final_url"] is None
    assert not any(h.startswith("/consistent") for h in site["site_hits"])


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


# ---------------------------------------------------------------- many vendors on one host


BIZ = {"alpha": "+14155550201", "alpha-two": "+14155550203", "beta": "+14155550202"}


async def test_businesses_sharing_a_host_each_see_only_their_own_number(site):
    import asyncio

    urls = {k: f"{site['site']}/shared_host/{k}/" for k in BIZ}
    rows = await asyncio.gather(*(check(u) for u in urls.values()))
    for key, row in zip(BIZ, rows):
        assert [p["phone"] for p in row["phones"]] == [BIZ[key]], key
        assert row["agreement"] == "consistent" and row["pages_crawled"] >= 2
        assert all(s["source_url"].startswith(urls[key]) for p in row["phones"] for s in p["sources"]), key
    assert "+14155550299" not in str(rows)  # the host root's own page is not in anyone's folder


async def test_no_request_leaves_the_folder_even_with_dot_segments_encoded_dots_and_absolute_links(site):
    await check(f"{site['site']}/shared_host/alpha/")
    paths = [h for h in site["site_hits"] if h != "/robots.txt"]
    assert paths and all(h.startswith("/shared_host/alpha/") for h in paths), paths
    assert not any(h.startswith(("/shared_host/beta", "/shared_host/alpha-two")) or h in ("/", "/shared_host/", "/shared_host") for h in paths)


async def test_the_folder_prefix_is_a_folder_not_a_string_prefix(site):
    await check(f"{site['site']}/shared_host/alpha/")
    assert not any(h.startswith("/shared_host/alpha-two") for h in site["site_hits"])  # alpha-two starts with the text "alpha"


async def test_extra_paths_resolve_inside_the_folder_and_cannot_climb_out(site):
    from src.crawl import crawl_site

    result = await crawl_site(f"{site['site']}/shared_host/alpha/", max_pages=10, extra_paths=["/team", "/../beta/contact.html", "../beta/", f"{site['site']}/shared_host/beta/"], timeout=5)
    assert "/shared_host/alpha/team" in site["site_hits"] and "/team" not in site["site_hits"]  # /team means <folder>/team, not the host root
    assert not any(h.startswith("/shared_host/beta") for h in site["site_hits"])
    assert {e.phone for e in result.evidence} == {BIZ["alpha"]} and result.outside_folder_skipped >= 3


async def test_a_site_at_a_domain_root_is_unchanged_the_prefix_is_slash(host):
    url, hits = host("consistent")  # this host serves the site at its root
    row = await check(url + "/")
    assert row["agreement"] == "consistent" and row["confidence"] == "high" and row["pages_crawled"] == 2 and row["primary_phone"] == "+14155550101"
    from src.crawl import Scope

    root = Scope(url + "/", "/")
    assert root.contains(url + "/") and root.contains(url + "/any/deep/page.html") and not root.contains("http://127.0.0.1:1/")
    assert Scope("https://acme.test/", "/").contains("https://www.acme.test/x")  # www and the bare domain are one site


def test_scope_decides_on_the_path_the_server_will_serve():
    from src.crawl import Scope, normal_path

    scope = Scope("https://h.test/Countersign/summit-concrete/", "/Countersign/summit-concrete/")
    inside = ["https://h.test/Countersign/summit-concrete/", "https://h.test/Countersign/summit-concrete", "https://h.test/Countersign/summit-concrete/contact.html",
              "https://h.test/Countersign/summit-concrete/a/../contact.html", "https://H.TEST/Countersign/summit-concrete//x"]
    outside = ["https://h.test/Countersign/summit-concrete-co/", "https://h.test/Countersign/", "https://h.test/", "https://h.test/countersign/summit-concrete/",
               "https://h.test/Countersign/summit-concrete/../northside-rentals/", "https://h.test/Countersign/summit-concrete/%2e%2e/northside-rentals/",
               "https://h.test/Countersign/summit-concrete/..%2fnorthside-rentals/", "https://h.test/Countersign/summit-concrete\\..\\northside-rentals/",
               "https://other.test/Countersign/summit-concrete/", "ftp://h.test/Countersign/summit-concrete/"]
    assert all(scope.contains(u) for u in inside), [u for u in inside if not scope.contains(u)]
    assert not any(scope.contains(u) for u in outside), [u for u in outside if scope.contains(u)]
    assert normal_path("/a//b/./c/../d/") == "/a/b/d/" and normal_path("/..") == "/" and normal_path("") == "/"


async def test_a_page_served_with_and_without_its_extension_is_fetched_once():
    import httpx

    from src.crawl import crawl_site, page_key

    assert page_key("https://h.test/a/contact") == page_key("https://h.test/a/contact.html") == page_key("https://h.test/a/contact.htm#x")
    assert page_key("https://h.test/a/") == page_key("https://h.test/a/index.html") and page_key("https://h.test/a/b") != page_key("https://h.test/a/c")
    served = []

    def handler(request: httpx.Request) -> httpx.Response:
        served.append(request.url.path)
        html = {"/a/": '<a href="contact.html">c</a><p>(415) 555-0100</p>', "/a/contact": "<h1>Contact</h1><p>(415) 555-0100</p>", "/a/contact.html": "<h1>Contact</h1><p>(415) 555-0100</p>"}
        return httpx.Response(200, text=html[request.url.path], headers={"content-type": "text/html"}) if request.url.path in html else httpx.Response(404)

    result = await crawl_site("https://h.test/a/", max_pages=10, extra_paths=["/contact"], timeout=2, transport=httpx.MockTransport(handler))
    assert result.pages_crawled == 2 and sorted(set(served) - {"/robots.txt"}) == ["/a/", "/a/contact.html"]  # the linked file is read first; the /contact guess is the same page
    assert len({e.source_url for e in result.evidence}) == 2
