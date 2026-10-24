# Vendor websites for the phone lookup

Our vendors are fictional, but their email domains (`summitconcrete.com`) may belong to real businesses. **The Apify Actor must never
crawl `email_domain`.** Every vendor has a separate `vendors.website_url` that points only at pages we host:

    <PAGES_BASE_URL>/<vendor-slug>/        e.g. https://aayushswami123.github.io/Countersign/summit-concrete/

`PAGES_BASE_URL` is a setting (`.env`, default `https://aayushswami123.github.io/Countersign`). The slug is the vendor name lowercased with
anything other than letters and digits turned into `-`. `email_domain` is unchanged and still used for the lookalike checks.

## Generating the sites

    cd backend
    python seed/seed.py          # fills vendors.website_url and the website contacts
    python -m seed.sites         # writes ../sites/ from the seeded database (deterministic, no timestamps)

`seed/sites.py` builds one small static site per vendor, plus the attacker's copy. Each vendor site has:

| File | Content |
|---|---|
| `index.html` | name, trade, short about text, footer phone with a `tel:` link, schema.org `LocalBusiness` JSON-LD |
| `contact.html` | the phone in visible text and a `tel:` link, the same JSON-LD |
| `sites/robots.txt` | `User-agent: *` / `Allow: /` |
| `sites/index.html` | a list of every site |
| `sites/.nojekyll` | stops GitHub Pages from running Jekyll |

Every page carries "Fictional company created for the Countersign hackathon demo."

Phones: Summit Concrete shows its on-file number, which is `DEMO_VENDOR_PHONE` when set (otherwise the fictional `+14155550100`).
Every other vendor shows its on-file `+1415555xxxx` number. The generator refuses to write a number that is not a 555 number, because
the sites are public; pass `--allow-real-phone` only if you mean it.

## Edge cases

| Vendor | Site | What the Actor sees |
|---|---|---|
| Alder Lumber Co | `alder-lumber-co/` | footer and JSON-LD on `index.html` show the on-file number, `contact.html` and its JSON-LD show a different one (`+14155550299`) |
| Redwood Paint and Coatings | `redwood-paint-and-coatings/` | no phone anywhere (pages, footer, JSON-LD) |
| Haulaway Dumpster Service | `haulaway-dumpster-service/` | `contact.html` does not exist; the "Contact" link is a 404 |
| (attacker) | `summit-concrete-co/` | a near copy of Summit Concrete's site with `+14155550166`, matching the lookalike domain `summit-concrete.co` of the bank-change attack. No vendor's `website_url` points at it |

## Publishing on GitHub Pages

Pages can publish a branch root or `/docs`, not an arbitrary `sites/` folder, so `.github/workflows/pages.yml` deploys `sites/` with
GitHub Actions. Nothing is published until you do these steps:

1. Make sure `sites/` and `.github/workflows/pages.yml` are committed and pushed to `main`.
2. GitHub, repository **Settings, Pages, Build and deployment, Source: GitHub Actions**. (Pages on a free account needs a public repository.)
3. Run the workflow: **Actions, Publish vendor sites, Run workflow** (it also runs on every push to `main` that changes `sites/`, and only then).
4. Open `https://aayushswami123.github.io/Countersign/` and check `.../summit-concrete/contact.html`, `.../robots.txt` and that `.../haulaway-dumpster-service/contact.html` is a 404.

If the repository or account name differs, set `PAGES_BASE_URL` to the real base URL, run `python seed/seed.py` and `python -m seed.sites`, and push again.

`robots.txt` allows everything. On a project site it lives under `/Countersign/`, not at the host root, so crawlers that only read
`https://aayushswami123.github.io/robots.txt` will not see it; Apify's crawlers allow crawling unless a robots.txt they read says no.

## Tests

`tests/test_sites.py` checks that every vendor has a website_url on our host, that no page links to an email domain, the phones in
each page and its JSON-LD, the edge cases, the attacker site, and that the output is byte-identical on a second run.
