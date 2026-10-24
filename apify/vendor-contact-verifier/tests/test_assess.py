"""Ranking, agreement and confidence from phone evidence."""

from src.assess import assess, build_row, failed_row, group
from src.crawl import CrawlResult
from src.phones import Evidence

A, B = "+14155550100", "+14155550177"


def ev(phone, found_in, url="https://v.test/"):
    return Evidence(phone, url, found_in)


def crawl(evidence, pages=2, reachable=True):
    return CrawlResult(evidence=evidence, pages_crawled=pages, site_reachable=reachable, final_url="https://v.test/")


def test_consistent_in_two_source_types_is_high():
    row = build_row("V", "https://v.test/", crawl([ev(A, "json_ld"), ev(A, "footer_text")]))
    assert (row["agreement"], row["confidence"], row["primary_phone"]) == ("consistent", "high", A)
    assert "2 source types" in row["confidence_reason"]


def test_consistent_in_one_source_type_is_medium_even_on_several_pages():
    row = build_row("V", "https://v.test/", crawl([ev(A, "tel_link", "https://v.test/"), ev(A, "tel_link", "https://v.test/contact")]))
    assert (row["agreement"], row["confidence"]) == ("consistent", "medium")
    assert "only one source type" in row["confidence_reason"]


def test_two_different_numbers_are_conflicting_and_low():
    row = build_row("V", "https://v.test/", crawl([ev(A, "json_ld"), ev(A, "footer_text"), ev(B, "contact_page_text")]))
    assert (row["agreement"], row["confidence"], row["primary_phone"]) == ("conflicting", "low", A)
    assert [p["phone"] for p in row["phones"]] == [A, B] and B in row["confidence_reason"]


def test_no_number_is_none_found_low_with_the_reason():
    assert assess([], crawl([], pages=3))[1:] == ("none_found", "low", "No phone number found on 3 page(s).")
    assert "could not be reached" in assess([], crawl([], pages=0, reachable=False))[3]
    assert "robots.txt" in assess([], crawl([], pages=0, reachable=True))[3]


def test_primary_is_the_number_with_the_most_independent_sources():
    ranked = group([ev(B, "json_ld"), ev(A, "tel_link"), ev(A, "footer_text"), ev(A, "footer_text", "https://v.test/contact")])
    assert [p["phone"] for p in ranked] == [A, B] and len(ranked[0]["sources"]) == 3


def test_ties_go_to_json_ld_then_the_contact_page_then_the_lower_number():
    assert group([ev(A, "footer_text"), ev(B, "json_ld")])[0]["phone"] == B
    assert group([ev(A, "footer_text"), ev(B, "other_text", "https://v.test/contact.html")])[0]["phone"] == B
    assert group([ev(A, "footer_text", "https://v.test/contact"), ev(B, "contact_page_text", "https://v.test/x")])[0]["phone"] in (A, B)
    assert group([ev(B, "other_text"), ev(A, "other_text")])[0]["phone"] == A  # fully tied: stable, not random


def test_rows_have_exactly_the_documented_fields():
    expected = ["name", "website_url", "primary_phone", "phones", "agreement", "confidence", "confidence_reason", "site_reachable", "final_url", "pages_crawled", "checked_at"]
    assert list(build_row("V", "https://v.test/", crawl([ev(A, "tel_link")])).keys()) == expected
    assert list(failed_row("V", "bad", "why").keys()) == expected
