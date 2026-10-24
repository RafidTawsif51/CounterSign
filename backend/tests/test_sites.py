"""The vendor websites the phone lookup crawls: hosted by us, never on a vendor's email domain."""

import json
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session, select

from app.config import get_settings
from app.models import ContactSource, Vendor, VendorContact
from seed import sites as sitesmod
from tests.conftest import copy_seeded

BASE = get_settings().pages_base_url.rstrip("/")


@pytest.fixture(scope="module")
def db(tmp_path_factory, seed_template):
    path = copy_seeded(seed_template, tmp_path_factory.mktemp("sites_db"), "sites.sqlite")
    with Session(create_engine(f"sqlite:///{path}")) as s:
        yield s


@pytest.fixture(scope="module")
def built(db, tmp_path_factory):
    out = tmp_path_factory.mktemp("sites_out")
    sites = sitesmod.build_sites(db)
    sitesmod.write_sites(sites, out)
    return out, {s.slug: s for s in sites}


def jsonld(path: Path) -> dict:
    return json.loads(re.search(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', path.read_text(), re.S).group(1))


def phones_in(text: str) -> set[str]:
    return set(re.findall(r"tel:(\+\d+)", text))


def phones(path: Path) -> set[str]:
    return set(re.findall(r"tel:(\+\d+)", path.read_text()))


# ---------------------------------------------------------------- the database side


def test_every_vendor_has_a_website_on_our_host(db):
    vendors = db.exec(select(Vendor)).all()
    assert len(vendors) == 30
    for v in vendors:
        assert v.website_url == f"{BASE}/{sitesmod.slugify(v.name)}/"
        assert v.email_domain not in v.website_url  # the real-looking domain is never the crawl target
    assert len({v.website_url for v in vendors}) == len(vendors)


def test_a_website_contact_points_at_the_hosted_contact_page_never_the_email_domain(db):
    vendors = {v.id: v for v in db.exec(select(Vendor))}
    for c in db.exec(select(VendorContact).where(VendorContact.source == ContactSource.website)):
        v = vendors[c.vendor_id]
        assert c.source_url == v.website_url + "contact.html"
    for c in db.exec(select(VendorContact)):
        assert c.source_url is None or vendors[c.vendor_id].email_domain not in c.source_url


def test_the_mock_phone_lookup_never_builds_a_url_from_the_email_domain():
    import asyncio

    from app.services import contacts

    for site in (None, f"{BASE}/x/"):
        v = Vendor(id="ven_t0", name="X", trade="t", email_domain="realbusiness.com", website_url=site)
        found = asyncio.run(contacts.lookup_phone(v))
        assert "realbusiness.com" not in found.source_url
        if found.source == "website":
            assert found.source_url == f"{BASE}/x/contact.html"


# ---------------------------------------------------------------- the sites


def test_one_site_per_vendor_plus_the_attacker_copy(built, db):
    out, sites = built
    assert len(sites) == 31 and sitesmod.ATTACKER_SLUG in sites
    for v in db.exec(select(Vendor)):
        assert (out / sitesmod.slugify(v.name) / "index.html").is_file()
    assert (out / "robots.txt").read_text() == "User-agent: *\nAllow: /\n"
    assert (out / "index.html").is_file() and (out / ".nojekyll").is_file()


def test_phones_follow_the_on_file_contact_and_are_fictional(built, db):
    out, sites = built
    on_file = {c.vendor_id: c.phone for c in db.exec(select(VendorContact).where(VendorContact.source == ContactSource.on_file))}
    summit = db.exec(select(Vendor).where(Vendor.id == "ven_summit")).one()
    assert phones(out / "summit-concrete" / "contact.html") == {on_file[summit.id]}  # DEMO_VENDOR_PHONE
    for v in db.exec(select(Vendor)):
        slug = sitesmod.slugify(v.name)
        if slug in (sitesmod.PHONE_MISMATCH, sitesmod.NO_PHONE, sitesmod.NO_CONTACT_PAGE):
            continue
        for page in ("index.html", "contact.html"):
            assert phones(out / slug / page) == {on_file[v.id]}, (slug, page)
            ld = jsonld(out / slug / page)
            assert ld["@type"] == "LocalBusiness" and ld["telephone"] == on_file[v.id] and ld["name"] == v.name
    for p in out.rglob("*.html"):
        assert all(sitesmod.is_fictional_phone(n) for n in re.findall(r"\+1\d{10}", p.read_text())), p


def test_contact_page_shows_the_number_in_visible_text_and_a_tel_link(built):
    out, _ = built
    text = (out / "keystone-steel-supply" / "contact.html").read_text()
    link = re.search(r'<a href="tel:(\+\d+)">([^<]+)</a>', text)
    assert link and sitesmod.display_phone(link.group(1)) == link.group(2)


def test_edge_case_phone_mismatch(built):
    out, _ = built
    d = out / sitesmod.PHONE_MISMATCH
    on_file = phones(d / "index.html")
    assert len(on_file) == 1 and sitesmod.MISMATCH_PHONE not in on_file  # the footer shows the on-file number
    assert phones(d / "contact.html") == on_file | {sitesmod.MISMATCH_PHONE}  # the contact page body shows another, under the same footer
    body = (d / "contact.html").read_text().split("<footer>")[0]
    assert sitesmod.MISMATCH_PHONE in body and not (on_file & phones_in(body))
    assert jsonld(d / "index.html")["telephone"] != jsonld(d / "contact.html")["telephone"]


def test_edge_case_no_phone_anywhere(built):
    out, _ = built
    for page in ("index.html", "contact.html"):
        text = (out / sitesmod.NO_PHONE / page).read_text()
        assert "tel:" not in text and "Phone:" not in text and "telephone" not in jsonld(out / sitesmod.NO_PHONE / page)
        assert not re.search(r"\d{3}\) \d{3}-\d{4}", text)


def test_edge_case_contact_page_missing(built):
    out, _ = built
    d = out / sitesmod.NO_CONTACT_PAGE
    assert (d / "index.html").is_file() and not (d / "contact.html").exists()
    assert 'href="contact.html"' in (d / "index.html").read_text()  # the link is there and 404s on the host


def test_attacker_site_is_a_near_copy_with_another_555_number(built):
    out, _ = built
    real, fake = out / "summit-concrete", out / sitesmod.ATTACKER_SLUG
    assert phones(fake / "contact.html") == phones(fake / "index.html") == {sitesmod.ATTACKER_PHONE}
    assert phones(fake / "contact.html") != phones(real / "contact.html")
    assert sitesmod.is_fictional_phone(sitesmod.ATTACKER_PHONE)
    assert jsonld(fake / "index.html")["name"] == jsonld(real / "index.html")["name"] == "Summit Concrete"
    assert jsonld(fake / "index.html")["url"] == f"{BASE}/{sitesmod.ATTACKER_SLUG}/"


def test_no_page_links_out_or_mentions_an_email_domain(built, db):
    out, _ = built
    domains = [v.email_domain for v in db.exec(select(Vendor))]
    for p in out.rglob("*.html"):
        text = p.read_text()
        assert not re.search(r'(href|src)="https?://', text), p
        assert not any(d in text for d in domains), p


def test_output_is_deterministic_and_stale_folders_are_removed(db, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    sitesmod.write_sites(sitesmod.build_sites(db), a)
    (a / "gone-vendor").mkdir()
    (a / "gone-vendor" / "index.html").write_text("old")
    sitesmod.write_sites(sitesmod.build_sites(db), a)
    sitesmod.write_sites(sitesmod.build_sites(db), b)
    files = lambda d: {p.relative_to(d).as_posix(): p.read_bytes() for p in d.rglob("*") if p.is_file()}  # noqa: E731
    assert files(a) == files(b) and not (a / "gone-vendor").exists()


def test_a_real_looking_phone_is_refused_unless_allowed(db):
    c = db.exec(select(VendorContact).where(VendorContact.id == "con_summit_1")).one()
    old = c.phone
    try:
        c.phone = "+14158675309"  # not in the 555 exchange
        db.add(c)
        db.flush()
        with pytest.raises(ValueError, match="555"):
            sitesmod.build_sites(db)
        assert sitesmod.build_sites(db, allow_real_phone=True)
    finally:
        db.rollback()
        c.phone = old


# ---------------------------------------------------------------- the published folder and its deploy


PUBLISHED = Path(__file__).resolve().parents[2] / "sites"
ROOT = Path(__file__).resolve().parents[2]


def test_vendor_website_urls_are_the_published_github_pages_urls(db):
    for v in db.exec(select(Vendor)):
        assert v.website_url == f"https://aayushswami123.github.io/Countersign/{sitesmod.slugify(v.name)}/", v.name


def test_the_committed_sites_folder_holds_only_fictional_phone_numbers():
    pages = list(PUBLISHED.rglob("*.html"))
    assert len(pages) >= 60, "run python -m seed.sites"
    seen = 0
    for p in pages:
        text = p.read_text()
        for number in re.findall(r"tel:(\+[\d]+)", text) + re.findall(r'"telephone": "(\+\d+)"', text):
            seen += 1
            assert re.fullmatch(r"\+1415555\d{4}", number), (p, number)
        for shown in re.findall(r"\(\d{3}\) \d{3}-\d{4}", text):
            assert re.fullmatch(r"\(415\) 555-\d{4}", shown), (p, shown)
        digits = re.sub(r"<script.*?</script>", "", text, flags=re.S)
        assert not re.search(r"(?<!\d)(?!415[ .-]?555)\d{3}[ .-]\d{3}[ .-]\d{4}(?!\d)", digits), p  # no other phone format either
    assert seen > 100


def test_every_link_in_the_committed_sites_is_relative_and_resolves():
    """The sites live under /Countersign/<slug>/, so a link that starts with / or http would leave them. Only Haulaway's contact link is
    allowed to be dead: it is the missing-contact-page edge case."""
    dead = []
    for p in PUBLISHED.rglob("*.html"):
        for href in re.findall(r'(?:href|src)="([^"]*)"', p.read_text()):
            assert not href.startswith(("/", "http:", "https:", "//")), (p, href)
            if href.startswith(("tel:", "mailto:", "#")):
                continue
            target = (p.parent / href).resolve()
            target = target / "index.html" if target.is_dir() else target
            if not target.is_file():
                dead.append((p.relative_to(PUBLISHED).as_posix(), href))
    assert set(dead) == {(f"{sitesmod.NO_CONTACT_PAGE}/index.html", "contact.html")}, dead
    assert PUBLISHED.joinpath(".nojekyll").is_file() and PUBLISHED.joinpath("robots.txt").is_file()


def test_the_pages_workflow_deploys_only_sites_with_the_official_actions():
    text = (ROOT / ".github" / "workflows" / "pages.yml").read_text()
    assert re.search(r"branches: \[main\]", text) and re.search(r'paths: \["sites/\*\*"\]', text)  # only a push to main that changes sites/
    for action in ("actions/configure-pages@", "actions/upload-pages-artifact@", "actions/deploy-pages@"):
        assert action in text, action
    assert re.search(r"upload-pages-artifact@v\d+\n\s+with:\n\s+path: sites\n", text)  # nothing but sites/ is uploaded
    assert "pages: write" in text and "id-token: write" in text
