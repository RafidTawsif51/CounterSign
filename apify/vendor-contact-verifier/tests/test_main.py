"""Input handling and per-business error handling."""

import pytest

from src import main as actor_main
from src.main import check_business, read_options, validate


def test_validate_names_the_problem():
    assert validate({"name": "A", "website_url": "https://a.test/"})[2] is None
    assert "name" in validate({"website_url": "https://a.test/"})[2]
    assert "http" in validate({"name": "A", "website_url": "a.test"})[2]
    assert "http" in validate({"name": "A", "website_url": "ftp://a.test"})[2]
    assert "object" in validate("https://a.test")[2]


def test_options_default_and_clamp():
    assert read_options({}) == (10, ["/contact", "/contact-us", "/about"], 15.0)
    assert read_options({"maxPagesPerSite": 500, "requestTimeoutSecs": 0, "extraPaths": []}) == (30, [], 15.0)
    assert read_options({"maxPagesPerSite": 2, "extraPaths": ["/team"], "requestTimeoutSecs": 3}) == (2, ["/team"], 3.0)


async def test_a_business_with_bad_input_becomes_a_low_confidence_row():
    row = await check_business({"name": "No Site", "website_url": ""}, 10, [], 5)
    assert row["name"] == "No Site" and row["confidence"] == "low" and row["site_reachable"] is False
    assert row["confidence_reason"].startswith("Not checked:") and row["pages_crawled"] == 0


async def test_an_unexpected_error_in_one_business_is_contained(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("parser exploded")

    monkeypatch.setattr(actor_main, "crawl_site", boom)
    row = await check_business({"name": "Bad", "website_url": "https://bad.test/"}, 10, [], 5)
    assert row["confidence"] == "low" and row["agreement"] == "none_found" and "RuntimeError" in row["confidence_reason"]
    assert set(row) >= {"name", "website_url", "primary_phone", "checked_at"}


async def test_one_failing_site_does_not_stop_the_others(site):
    rows = [await check_business(b, 10, ["/contact"], 3) for b in (
        {"name": "Down", "website_url": "http://127.0.0.1:1/"},
        {"name": "Acme", "website_url": f"{site['site']}/consistent/"},
        {"name": "Broken", "website_url": "nope"},
    )]
    assert [r["name"] for r in rows] == ["Down", "Acme", "Broken"]
    assert [r["confidence"] for r in rows] == ["low", "high", "low"] and rows[1]["primary_phone"] == "+14155550101"
