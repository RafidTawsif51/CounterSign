# Vendor Contact Verifier

Find a vendor's real phone number on the vendor's own website, with proof of where it was found, before you call to confirm a bank change.

## What it does and why

Payment fraud often starts with an email that says "we changed banks". The email comes with a phone number to call and "confirm". That number belongs to the scammer. The safe move is to call a number that does not come from the email: one published on the vendor's own website.

Vendor Contact Verifier does that lookup. For each business you give it, the Actor reads the business's own website (`website_url`) and returns:

- the phone number it found (`primary_phone`), in E.164 format,
- every page and place that number appeared (`sources`: `source_url` and `found_in`),
- whether the website agrees with itself (`agreement`),
- how much to trust the result (`confidence` and `confidence_reason`).

You get proof, not just a number: "this number is in the page's JSON-LD, in a `tel:` link and in the footer of two pages".

## Who it is for

- Accounts payable teams and AP automation that call a vendor to confirm a bank detail change.
- Fraud and risk teams that need an independent callback number.
- Anyone who needs a business phone number from the business's own site, with sources, at small scale.

## How it works

For each object in `businesses` the Actor:

1. Reads `robots.txt` at the root of the host of `website_url` and obeys it.
2. Fetches the homepage, then each path in `extraPaths`, then in-scope links found on those pages (links that look like contact or about pages first), up to `maxPagesPerSite` requests.
3. Extracts phone numbers from `tel:` links, schema.org JSON-LD (`Organization` and `LocalBusiness`, including `contactPoint`) and visible text. It ignores numbers inside scripts, forms, hidden elements and comments.
4. Normalizes every number to E.164 with the `phonenumbers` library. Numbers written without a country code are read as US/Canada numbers.
5. Records, for every number, each `source_url` and `found_in`.
6. Picks `primary_phone`, sets `agreement` and `confidence`, and writes one dataset row.

**Scope.** Only URLs on the host of `website_url` **and under its folder** are ever requested. For `https://example.org/directory/acme/` that is `/directory/acme/` and everything below it. For a site at a domain root the folder is `/`, so the whole host is in scope and nothing changes for ordinary websites. Many businesses can share one host (a directory, GitHub Pages, a marketplace), so a link to a neighbour's folder, a link to another host, and a redirect to either are not followed. `..` segments and encoded dots such as `%2e%2e` are resolved before the check, so a link cannot climb out of the folder. `example.com` and `www.example.com` count as the same host. A business that fails, or has bad input, becomes a row with `confidence` `low`. It never fails the run.

## Input

| Field | Type | Default | Description |
|---|---|---|---|
| `businesses` | array of `{name, website_url}` | required | The businesses to check. `website_url` is the business's own website, a full `https://` URL **from your vendor records, never from an email**. |
| `maxPagesPerSite` | integer, 1 to 30 | 10 | The most requests per website. A request that fails (a 404) counts. |
| `extraPaths` | array of strings | `["/contact", "/contact-us", "/about"]` | Pages to try besides the homepage. Resolved inside the folder of `website_url`: for `https://host/shop/`, `/contact` means `https://host/shop/contact`. A path that would leave the folder is skipped. |
| `requestTimeoutSecs` | integer, 1 to 120 | 15 | How long to wait for one page. |

### Example input

This is also the default input, so a run with no changes checks Summit Concrete, a fictional vendor whose pages we host on GitHub Pages. The folder of the `website_url` is the boundary of the crawl.

```json
{
  "businesses": [
    { "name": "Summit Concrete", "website_url": "https://aayushswami123.github.io/Countersign/summit-concrete/" }
  ],
  "maxPagesPerSite": 10,
  "extraPaths": ["/contact", "/contact-us", "/about"],
  "requestTimeoutSecs": 15
}
```

## Output

One dataset row per business, in input order. The same fields are described in the dataset schema and shown in the Apify Console table view.

| Field | Description |
|---|---|
| `name` | The business name from the input. |
| `website_url` | The `website_url` from the input: the only website, and folder, that was crawled. |
| `primary_phone` | The number with the most independent `sources`, in E.164 format, or `null` when `agreement` is `none_found`. Ties go to a number in JSON-LD, then to one on the contact page. |
| `phones` | Every number found, best supported first. Each has `phone` and `sources`. |
| `phones[].sources[].source_url` | The page the number was found on. |
| `phones[].sources[].found_in` | One of `tel_link`, `json_ld`, `contact_page_text`, `footer_text`, `other_text`. |
| `agreement` | `consistent` (one number), `conflicting` (more than one) or `none_found`. |
| `confidence` | `high`, `medium` or `low`. See the rules below. |
| `confidence_reason` | A short sentence explaining `confidence`. |
| `site_reachable` | `true` when at least one page was read, or `robots.txt` answered but disallows crawling. |
| `final_url` | The homepage URL after redirects inside the folder, or `null` when the site was not reached. |
| `pages_crawled` | How many pages were read successfully. |
| `checked_at` | When the check finished, ISO 8601 in UTC. |

A **source** is one `source_url` and `found_in` pair, so the same number in the JSON-LD and in the footer of one page is two sources. A **source type** is a `found_in` value.

### Example output

The row for the default input, from a real run:

```json
{
  "name": "Summit Concrete",
  "website_url": "https://aayushswami123.github.io/Countersign/summit-concrete/",
  "primary_phone": "+14155550100",
  "phones": [
    {
      "phone": "+14155550100",
      "sources": [
        { "source_url": "https://aayushswami123.github.io/Countersign/summit-concrete/", "found_in": "json_ld" },
        { "source_url": "https://aayushswami123.github.io/Countersign/summit-concrete/", "found_in": "tel_link" },
        { "source_url": "https://aayushswami123.github.io/Countersign/summit-concrete/", "found_in": "footer_text" },
        { "source_url": "https://aayushswami123.github.io/Countersign/summit-concrete/contact.html", "found_in": "json_ld" },
        { "source_url": "https://aayushswami123.github.io/Countersign/summit-concrete/contact.html", "found_in": "tel_link" },
        { "source_url": "https://aayushswami123.github.io/Countersign/summit-concrete/contact.html", "found_in": "footer_text" },
        { "source_url": "https://aayushswami123.github.io/Countersign/summit-concrete/contact.html", "found_in": "contact_page_text" }
      ]
    }
  ],
  "agreement": "consistent",
  "confidence": "high",
  "confidence_reason": "One number, found in 4 source types (contact page text, footer text, JSON-LD, tel link) on 2 page(s).",
  "site_reachable": true,
  "final_url": "https://aayushswami123.github.io/Countersign/summit-concrete/",
  "pages_crawled": 2,
  "checked_at": "2026-10-24T20:32:15+00:00"
}
```

A website that disagrees with itself (Alder Lumber Co, another fictional vendor we host: its footer shows one number and its contact page another):

```json
{
  "name": "Alder Lumber Co",
  "website_url": "https://aayushswami123.github.io/Countersign/alder-lumber-co/",
  "primary_phone": "+14155550103",
  "phones": [
    {
      "phone": "+14155550103",
      "sources": [
        { "source_url": "https://aayushswami123.github.io/Countersign/alder-lumber-co/", "found_in": "json_ld" },
        { "source_url": "https://aayushswami123.github.io/Countersign/alder-lumber-co/", "found_in": "tel_link" },
        { "source_url": "https://aayushswami123.github.io/Countersign/alder-lumber-co/", "found_in": "footer_text" },
        { "source_url": "https://aayushswami123.github.io/Countersign/alder-lumber-co/contact.html", "found_in": "tel_link" },
        { "source_url": "https://aayushswami123.github.io/Countersign/alder-lumber-co/contact.html", "found_in": "footer_text" }
      ]
    },
    {
      "phone": "+14155550299",
      "sources": [
        { "source_url": "https://aayushswami123.github.io/Countersign/alder-lumber-co/contact.html", "found_in": "json_ld" },
        { "source_url": "https://aayushswami123.github.io/Countersign/alder-lumber-co/contact.html", "found_in": "tel_link" },
        { "source_url": "https://aayushswami123.github.io/Countersign/alder-lumber-co/contact.html", "found_in": "contact_page_text" }
      ]
    }
  ],
  "agreement": "conflicting",
  "confidence": "low",
  "confidence_reason": "2 different numbers found: +14155550103 (5 sources), +14155550299 (3 sources). Do not call until a person has checked.",
  "site_reachable": true,
  "final_url": "https://aayushswami123.github.io/Countersign/alder-lumber-co/",
  "pages_crawled": 2,
  "checked_at": "2026-10-24T20:32:15+00:00"
}
```

## Confidence rules

| `agreement` | Found in | `confidence` |
|---|---|---|
| `consistent` (one number) | 2 or more source types | `high` |
| `consistent` (one number) | 1 source type | `medium` |
| `conflicting` (more than one number) | any | `low` |
| `none_found` | nothing, or the site could not be read | `low` |

With `conflicting`, `primary_phone` is only the best-supported guess. Have a person check the website before calling.

## Run it from code

### Python

```python
from apify_client import ApifyClient

client = ApifyClient("<YOUR_API_TOKEN>")
run = client.actor("<YOUR_USERNAME>/vendor-contact-verifier").call(run_input={
    "businesses": [{"name": "Summit Concrete", "website_url": "https://aayushswami123.github.io/Countersign/summit-concrete/"}],
})
for row in client.dataset(run["defaultDatasetId"]).iterate_items():
    print(row["name"], row["primary_phone"], row["agreement"], row["confidence"])
```

### cURL

```bash
curl -X POST "https://api.apify.com/v2/acts/<YOUR_USERNAME>~vendor-contact-verifier/run-sync-get-dataset-items?token=<YOUR_API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"businesses": [{"name": "Summit Concrete", "website_url": "https://aayushswami123.github.io/Countersign/summit-concrete/"}]}'
```

## Pricing and cost

The Actor uses Apify's pay-per-usage model: you pay only for the platform usage of your runs, with no extra fee per result. Almost all of a run is spent waiting for the websites, so the cost grows with the number of `businesses` and with `maxPagesPerSite`. A real run on 24 October 2026 checked 6 businesses (9 pages) in 3 seconds and used about $0.00025 of platform usage, around $0.00004 per business. Lower `maxPagesPerSite` and `requestTimeoutSecs` to make slow websites cheaper.

## Integrations and scheduling

- **Apify API and clients.** Call the Actor from Python or JavaScript as shown above, or with the cURL endpoint that waits for the run and returns the dataset rows.
- **Schedules and webhooks.** Re-check your vendors' websites on a schedule, or start a run from a webhook when a bank change request arrives, and read the dataset when the run finishes.
- **No-code tools.** Use Apify's integrations (Make, Zapier, n8n and others) to send each row to your accounts payable tool.
- **AI agents.** An agent can call the Actor as a tool, for example through the Apify MCP server, and use `primary_phone`, `agreement` and `confidence` to decide whether to place a verification call.

## FAQ

**Does it phone the vendor?** No. It only reads websites. It gives you a number to call, and the proof of where the number came from.

**Where should `website_url` come from?** From your own vendor records, set up before any change request. Never from the email that asks for the change.

**What if `agreement` is `conflicting`?** The website lists more than one number. `primary_phone` is only the best-supported guess. Have a person look at the pages in `sources` before anyone calls.

**What if `agreement` is `none_found`?** The pages had no phone number, the website could not be reached (`site_reachable` is `false`), or `robots.txt` does not allow crawling. `confidence_reason` says which.

**Does it work on websites that need JavaScript?** No. It reads the HTML the server sends, so numbers added by scripts are missed.

**Which numbers does it return?** Phone numbers in E.164 format. A number written without a country code is read as a US/Canada number.

**Will it crawl a whole site?** No. It reads at most `maxPagesPerSite` pages, all inside the folder of `website_url`.

## Support

Found a website where the result is wrong, or want another field? Open an issue on the Actor's page in Apify Console (Issues tab) and include the `website_url` and the row you got.

## Limitations

- **Public pages only.** No logins, cookies or forms. Pages behind bot protection or a login are reported with `site_reachable` `false` or `none_found`.
- **No JavaScript rendering.** The Actor reads the HTML the server sends. A number that a script adds to the page is not seen. JSON-LD and `tel:` links in the HTML are.
- **A website can be changed by an attacker who controls it.** A number on the site proves only that the site says so. A scammer who owns a lookalike domain, or who breaks into the real site, can publish their own number, and the Actor will report it with `high` confidence. Take `website_url` from your own vendor records, never from the email that asks for the change, and compare the result with the number you already have on file. A different number is a reason to stop.
- **A number is not an identity check.** It tells you where to call, not who will answer.
- Numbers written without a country code are read as US/Canada numbers.
- `maxPagesPerSite` limits requests, including ones that fail. Pages larger than 2 MB are cut off.
- **A folder is the boundary, not an identity.** On a shared host the Actor stays inside the folder of `website_url` (`/org/acme/`), so a neighbour's number cannot be mixed in. It cannot tell whether the folder really belongs to the business: that is the same trust in `website_url` as above. Give it the exact folder URL, with the folder's own path, and not the host's root.
- A website whose pages link only to pages outside its own folder (for example a site that keeps its contact page at the host root while `website_url` is a sub-folder) will be reported `none_found`. Give the Actor the URL whose folder holds the pages.
- `robots.txt` is read at the host root. A site published under a path of a shared host (for example `host/org/site/`) is governed by the host's `robots.txt`, not one inside the path.

## Privacy

- The Actor reads only pages that the business itself has made public, and only inside the host and folder of the `website_url` you give it. It sends no cookies and submits no forms.
- It obeys `robots.txt` and identifies itself with the user agent `VendorContactVerifier/1.0`.
- It collects business phone numbers published by the business. If a website lists a person's own number, that number appears in the output. Handle the dataset as you would any vendor contact data and follow the privacy rules that apply to you.
- The input and output stay in your Apify run storage. Nothing is sent anywhere else.

## Run and test locally

```bash
pip install -r requirements-dev.txt
pytest                      # local fixtures only, no internet
apify run                   # reads storage/key_value_stores/default/INPUT.json
```

See [CHANGELOG.md](CHANGELOG.md) for what changed in each version.
