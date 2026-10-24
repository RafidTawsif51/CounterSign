"""Static vendor websites for the Apify phone lookup.

    cd backend && python -m seed.sites            # writes ../sites/ from the seeded database
    python seed/sites.py --out /tmp/sites

Our vendors are fictional, but their email domains (summitconcrete.com) may belong to real businesses, so the
Actor must never crawl them. Every vendor gets its own website_url that points only at pages we host:
<PAGES_BASE_URL>/<vendor-slug>/. One small static site per vendor is generated here from the seeded rows: the vendor's name
and trade, the on-file phone in the footer, a contact page and schema.org LocalBusiness JSON-LD. Output is deterministic (no
timestamps), so a rebuild only changes files when the seed does.

Edge cases the lookup has to survive (one vendor each):
  PHONE_MISMATCH   footer and contact page show different numbers (the contact page's JSON-LD follows its page)
  NO_PHONE         no phone anywhere on the site
  NO_CONTACT_PAGE  contact.html does not exist (the link 404s)
And sites/summit-concrete-co/ is the attacker's near copy of Summit Concrete's site, with a different 555 number, matching the
lookalike domain (summit-concrete.co) of the bank-change attack.

Phones: the Summit Concrete site uses the on-file number, which is DEMO_VENDOR_PHONE when set. Every other vendor uses its
on-file fictional 555 number. A number outside 555 would be published to a public site, so the generator refuses unless
--allow-real-phone is given.
"""

import argparse
import hashlib
import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.models import ContactSource, Vendor, VendorContact  # noqa: E402

SITES_DIR = Path(__file__).resolve().parents[2] / "sites"

PHONE_MISMATCH = "alder-lumber-co"
NO_PHONE = "redwood-paint-and-coatings"
NO_CONTACT_PAGE = "haulaway-dumpster-service"
MISMATCH_PHONE = "+14155550299"  # shown on the mismatch vendor's contact page
ATTACKER_SLUG = "summit-concrete-co"
ATTACKER_PHONE = "+14155550166"
SUMMIT_SLUG = "summit-concrete"

FICTION = "Fictional company created for the Countersign hackathon demo. Not a real business."

ABOUT = {
    "concrete": "Ready-mix concrete, delivered on schedule to job sites across the Bay Area. Foundations, slabs, flatwork and pumped pours.",
    "steel": "Structural steel, rebar accessories and cut-to-length fabrication for commercial builders.",
    "lumber": "Framing lumber, sheet goods and engineered beams, with yard pickup and same-week delivery.",
    "electrical supply": "Wire, conduit, panels and lighting for electrical contractors, with a trade counter open early.",
    "aggregates": "Crushed aggregate base, sand and drain rock, hauled to site by our own fleet.",
    "rebar": "Cut and bent rebar, mesh and tie wire for foundations and slabs, ready for pickup or delivery.",
    "glazing": "Storefront, curtain wall and residential glazing, measured, fabricated and installed.",
    "paint": "Commercial coatings, primers and color matching for contractors and painters.",
    "hardware": "Fasteners, anchors and tools for the trades, in stock and by the case.",
    "fuel": "On-site diesel and lubricant delivery for equipment fleets and job sites.",
    "safety equipment": "Hard hats, fall protection, signage and site safety supplies for construction crews.",
    "drywall": "Drywall, framing and finishing supplies delivered to the floor you are working on.",
    "electrical": "Commercial electrical contractors: new construction, tenant improvements and service.",
    "plumbing": "Plumbing and hydronic heating for commercial and multifamily construction.",
    "hvac": "HVAC design, installation and service for commercial buildings.",
    "excavation": "Site excavation, grading and utility trenching with our own equipment and operators.",
    "framing": "Wood framing and finish carpentry for commercial and residential builders.",
    "roofing": "Commercial and residential roofing: new roofs, re-roofs and repairs.",
    "painting": "Interior and exterior painting for commercial and multifamily projects.",
    "landscaping": "Landscape installation, irrigation and maintenance for new developments.",
    "masonry": "Brick, block and stone masonry for structural and architectural work.",
    "surveying": "Boundary, topographic and construction staking surveys.",
    "paving": "Asphalt paving, patching and striping for lots and roads.",
    "insulation": "Spray foam, batt and blown-in insulation for new construction and retrofits.",
    "equipment rental": "Excavators, lifts and compact equipment for daily, weekly and monthly rental.",
    "crane rental": "Mobile and tower crane rental with certified operators and rigging crews.",
    "scaffolding rental": "Scaffolding, shoring and access equipment, delivered, erected and dismantled.",
    "site services": "Portable restrooms, site fencing and temporary power for active job sites.",
    "waste hauling": "Roll-off dumpsters and debris hauling for construction and demolition.",
    "crane hire": "One-day crane hire with operator, booked by phone.",
}
ACCENTS = ["#1f4e79", "#2e6f40", "#8a3b12", "#5b3a8a", "#8a1f3d", "#0f6b75", "#4a4a4a", "#6b5b00"]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def website_url(name: str, base: Optional[str] = None) -> str:
    """The only site the phone lookup may crawl for this vendor: a page we host."""
    return f"{(base if base is not None else get_settings().pages_base_url).rstrip('/')}/{slugify(name)}/"


def contact_url(name: str, base: Optional[str] = None) -> str:
    return website_url(name, base) + "contact.html"


def display_phone(e164: str) -> str:
    d = re.sub(r"\D", "", e164)[-10:]
    return f"({d[:3]}) {d[3:6]}-{d[6:]}"


def is_fictional_phone(e164: str) -> bool:
    return bool(re.fullmatch(r"\+1\d{3}555\d{4}", e164))


@dataclass
class Site:
    slug: str
    name: str
    trade: str
    url: str
    footer_phone: Optional[str]  # E.164
    contact_phone: Optional[str]
    has_contact_page: bool = True


# ---------------------------------------------------------------- rendering


def _css(slug: str) -> str:
    accent = ACCENTS[int(hashlib.sha256(slug.encode()).hexdigest()[:4], 16) % len(ACCENTS)]
    return f"""
:root {{ --accent: {accent}; --ink: #1d2328; --muted: #5d6870; --rule: #dde2e6; --bg: #f7f8f9; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; font: 16px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: var(--ink); background: var(--bg); }}
header {{ background: #fff; border-bottom: 3px solid var(--accent); }}
.wrap {{ max-width: 760px; margin: 0 auto; padding: 0 20px; }}
header .wrap {{ display: flex; align-items: baseline; justify-content: space-between; gap: 16px; padding-top: 18px; padding-bottom: 14px; flex-wrap: wrap; }}
.brand {{ font-size: 22px; font-weight: 700; color: var(--accent); text-decoration: none; }}
nav a {{ margin-left: 18px; color: var(--ink); text-decoration: none; font-size: 15px; }}
nav a:hover {{ color: var(--accent); }}
main {{ padding: 36px 0 48px; }}
h1 {{ font-size: 30px; line-height: 1.2; margin: 0 0 6px; }}
.trade {{ color: var(--muted); text-transform: capitalize; margin: 0 0 22px; }}
.card {{ background: #fff; border: 1px solid var(--rule); border-radius: 8px; padding: 20px 22px; margin-top: 22px; }}
.card h2 {{ font-size: 17px; margin: 0 0 8px; }}
.phone {{ font-size: 24px; font-weight: 600; }}
.phone a {{ color: var(--accent); text-decoration: none; }}
footer {{ border-top: 1px solid var(--rule); background: #fff; padding: 18px 0 26px; font-size: 14px; color: var(--muted); }}
footer p {{ margin: 2px 0; }}
.fiction {{ font-size: 12px; margin-top: 10px; }}
"""


def _jsonld(site: Site, phone: Optional[str]) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": site.name,
        "description": ABOUT.get(site.trade, f"{site.name}: {site.trade}."),
        "url": site.url,
        "areaServed": "San Francisco Bay Area",
    }
    if phone:
        data["telephone"] = phone
    # Escape "<" so no string can close the script block.
    return json.dumps(data, indent=2).replace("<", "\\u003c")


def _page(site: Site, title: str, body: str, phone_in_footer: Optional[str], jsonld_phone: Optional[str]) -> str:
    esc = html.escape
    nav = '<a href="index.html">Home</a><a href="contact.html">Contact</a>'  # contact.html is missing for NO_CONTACT_PAGE, on purpose
    footer_phone = f'<p>Phone: <a href="tel:{phone_in_footer}">{display_phone(phone_in_footer)}</a></p>' if phone_in_footer else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(ABOUT.get(site.trade, site.name))}">
<style>{_css(site.slug)}</style>
<script type="application/ld+json">
{_jsonld(site, jsonld_phone)}
</script>
</head>
<body>
<header><div class="wrap"><a class="brand" href="index.html">{esc(site.name)}</a><nav>{nav}</nav></div></header>
<main><div class="wrap">
{body}
</div></main>
<footer><div class="wrap">
<p><strong>{esc(site.name)}</strong>, {esc(site.trade)}, San Francisco Bay Area</p>
{footer_phone}
<p class="fiction">{esc(FICTION)}</p>
</div></footer>
</body>
</html>
"""


def render_index(site: Site) -> str:
    esc = html.escape
    body = f"""<h1>{esc(site.name)}</h1>
<p class="trade">{esc(site.trade)}</p>
<p>{esc(ABOUT.get(site.trade, f"{site.name} serves builders across the Bay Area."))}</p>
<div class="card"><h2>About us</h2>
<p>We work with general contractors on schedule-driven jobs and invoice weekly. Questions about an order or an invoice? Call or email our office during business hours, Monday to Friday, 7 am to 5 pm.</p></div>"""
    return _page(site, f"{site.name} | {site.trade}", body, site.footer_phone, site.footer_phone)


def render_contact(site: Site) -> str:
    esc = html.escape
    if site.contact_phone:
        phone = f'<p class="phone">Phone: <a href="tel:{site.contact_phone}">{display_phone(site.contact_phone)}</a></p>'
    else:
        phone = "<p>Please use the form on our office desk or email us. We reply within one business day.</p>"
    body = f"""<h1>Contact {esc(site.name)}</h1>
<p class="trade">Accounts and dispatch</p>
<div class="card"><h2>Office</h2>
{phone}
<p>Monday to Friday, 7 am to 5 pm Pacific.</p></div>"""
    return _page(site, f"Contact | {site.name}", body, site.footer_phone, site.contact_phone)


def render_root(sites: list[Site]) -> str:
    esc = html.escape
    items = "\n".join(f'<li><a href="{esc(s.slug)}/">{esc(s.name)}</a></li>' for s in sorted(sites, key=lambda s: s.slug))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Countersign demo vendor sites</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;color:#1d2328}}li{{margin:2px 0}}p.f{{color:#5d6870;font-size:13px}}</style></head>
<body><h1>Countersign demo vendor sites</h1>
<p>One small website per fictional vendor of Ridgeline Builders, for testing a phone lookup. {esc(FICTION)}</p>
<ul>
{items}
</ul>
</body></html>
"""


# ---------------------------------------------------------------- building


def build_sites(session: Session, base: Optional[str] = None, *, allow_real_phone: bool = False) -> list[Site]:
    """One Site per vendor in the database, plus the attacker's copy of Summit Concrete."""
    on_file = {c.vendor_id: c.phone for c in session.exec(select(VendorContact).where(VendorContact.source == ContactSource.on_file))}
    sites: list[Site] = []
    seen: set[str] = set()
    for v in session.exec(select(Vendor).order_by(Vendor.id)).all():
        slug = slugify(v.name)
        if slug in seen or slug == ATTACKER_SLUG:
            raise ValueError(f"two vendors would share the site folder {slug}")
        seen.add(slug)
        phone = on_file.get(v.id)
        if phone and not is_fictional_phone(phone) and not allow_real_phone:
            raise ValueError(
                f"{v.name}'s on-file phone is not a 555 number (DEMO_VENDOR_PHONE?). Generated sites are published, so a real number "
                "would become public. Use a fictional number, or pass --allow-real-phone if you accept that.")
        footer = phone
        contact = phone
        has_contact = True
        if slug == PHONE_MISMATCH:
            contact = MISMATCH_PHONE
        elif slug == NO_PHONE:
            footer = contact = None
        elif slug == NO_CONTACT_PAGE:
            has_contact = False
        sites.append(Site(slug, v.name, v.trade, website_url(v.name, base), footer, contact, has_contact))
    summit = next((s for s in sites if s.slug == SUMMIT_SLUG), None)
    if summit is not None:
        b = (base if base is not None else get_settings().pages_base_url).rstrip("/")
        sites.append(Site(ATTACKER_SLUG, summit.name, summit.trade, f"{b}/{ATTACKER_SLUG}/", ATTACKER_PHONE, ATTACKER_PHONE))
    return sites


def write_sites(sites: list[Site], out: Path = SITES_DIR) -> list[Path]:
    """Write every site, robots.txt and a root index. Stale vendor folders are removed so a rename leaves nothing behind."""
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def put(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)

    wanted = {s.slug for s in sites}
    for old in out.iterdir():
        if old.is_dir() and old.name not in wanted:
            for f in old.iterdir():
                f.unlink()
            old.rmdir()
    for s in sites:
        put(out / s.slug / "index.html", render_index(s))
        contact = out / s.slug / "contact.html"
        if s.has_contact_page:
            put(contact, render_contact(s))
        else:
            contact.unlink(missing_ok=True)
    put(out / "robots.txt", "User-agent: *\nAllow: /\n")
    put(out / ".nojekyll", "")
    put(out / "index.html", render_root(sites))
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=SITES_DIR)
    parser.add_argument("--allow-real-phone", action="store_true")
    args = parser.parse_args()
    from app.db import engine

    with Session(engine) as s:
        sites = build_sites(s, allow_real_phone=args.allow_real_phone)
    files = write_sites(sites, args.out)
    print(f"{len(sites)} sites, {len(files)} files in {args.out}")


if __name__ == "__main__":
    main()
