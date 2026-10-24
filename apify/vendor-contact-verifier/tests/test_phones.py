"""Phone extraction from one HTML page."""

from src.phones import Evidence, extract_page, normalize

URL = "https://vendor.test/contact.html"


def found(html: str, url: str = URL) -> set[tuple[str, str]]:
    return {(e.phone, e.found_in) for e in extract_page(html, url).evidence}


def test_normalizes_every_common_way_of_writing_a_number_to_e164():
    for raw in ("(415) 555-0100", "415-555-0100", "415.555.0100", "+1 415 555 0100", "+14155550100", "1-415-555-0100"):
        assert normalize(raw) == "+14155550100", raw
    assert normalize("+44 20 7946 0958") == "+442079460958"


def test_things_that_are_not_a_dialable_number_are_refused():
    for raw in ("555-0100", "94105", "hello", "12", ""):
        assert normalize(raw) is None, raw


def test_tel_link_is_found_and_normalized():
    assert found('<a href="tel:+1-415-555-0100">x</a>') == {("+14155550100", "tel_link")}
    assert found('<a href="tel:(415)%20555-0100;ext=5">x</a>') == {("+14155550100", "tel_link")}


def test_json_ld_organization_and_local_business_and_contact_point():
    ld = '<script type="application/ld+json">{}</script>'
    one = ld.replace("{}", '{"@type":"LocalBusiness","telephone":"+1 415-555-0100"}')
    two = ld.replace("{}", '{"@graph":[{"@type":"Organization","contactPoint":[{"@type":"ContactPoint","telephone":"415-555-0101"}]}]}')
    assert found(one) == {("+14155550100", "json_ld")}
    assert found(two) == {("+14155550101", "json_ld")}
    other = ld.replace("{}", '{"@type":"Person","telephone":"+14155550102"}')
    assert found(other) == set()  # only organizations and businesses count
    assert found(ld.replace("{}", "{broken json")) == set()


def test_text_is_classified_by_where_it_sits():
    html = "<body><h1>Hello</h1><p>Call (415) 555-0100</p><footer>Office (415) 555-0101</footer></body>"
    assert found(html, "https://vendor.test/") == {("+14155550100", "other_text"), ("+14155550101", "footer_text")}
    assert ("+14155550100", "contact_page_text") in found(html, "https://vendor.test/contact-us")
    assert ("+14155550100", "contact_page_text") in found("<h1>Contact us</h1><p>(415) 555-0100</p>", "https://vendor.test/x.html")
    assert ("+14155550101", "footer_text") in found('<div id="site-footer">(415) 555-0101</div>')


def test_numbers_in_scripts_forms_hidden_elements_and_comments_are_ignored():
    html = """<body>
      <script>var p = '(415) 555-0111';</script><style>/* (415) 555-0112 */</style><noscript>(415) 555-0113</noscript>
      <form><p>Call (415) 555-0114</p><input placeholder="(415) 555-0115"></form>
      <div style="display: none">(415) 555-0116</div><div hidden>(415) 555-0117</div><p aria-hidden="true">(415) 555-0118</p>
      <p style="visibility:hidden">(415) 555-0119</p><!-- (415) 555-0120 -->
      <div><span hidden><a href="tel:+14155550121">x</a></span></div>
    </body>"""
    assert found(html) == set()


def test_bare_digit_runs_dates_and_zip_codes_are_not_phones():
    assert found("<p>Order 4155550188, zip 94105, due 2026-11-18, ref 20261118123</p>") == set()


def test_same_number_on_one_page_in_one_place_is_one_piece_of_evidence():
    page = extract_page('<a href="tel:+14155550100">a</a><a href="tel:4155550100">b</a>', URL)
    assert page.evidence == [Evidence("+14155550100", URL, "tel_link")]


def test_links_are_returned_absolute_without_fragments_and_without_tel_or_mailto():
    html = '<a href="/a#top">A</a><a href="b.html">B</a><a href="mailto:x@y.z">m</a><a href="tel:+14155550100">t</a><a href="https://o.test/z">Z</a><p hidden><a href="/h">h</a></p>'
    assert [h for h, _ in extract_page(html, "https://vendor.test/dir/index.html").links] == ["https://vendor.test/a", "https://vendor.test/dir/b.html", "https://o.test/z"]
