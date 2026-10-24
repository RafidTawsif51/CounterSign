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

1. Reads `robots.txt` on the host of `website_url` and obeys it.
2. Fetches the homepage, then each path in `extraPaths`, then same-host links found on those pages (links that look like contact or about pages first), up to `maxPagesPerSite` requests.
3. Extracts phone numbers from `tel:` links, schema.org JSON-LD (`Organization` and `LocalBusiness`, including `contactPoint`) and visible text. It ignores numbers inside scripts, forms, hidden elements and comments.
4. Normalizes every number to E.164 with the `phonenumbers` library. Numbers written without a country code are read as US/Canada numbers.
5. Records, for every number, each `source_url` and `found_in`.
6. Picks `primary_phone`, sets `agreement` and `confidence`, and writes one dataset row.

Only the host of `website_url` is ever requested. A link to another host is not followed, and neither is a redirect to another host (`example.com` and `www.example.com` count as the same host). A business that fails, or has bad input, becomes a row with `confidence` `low`. It never fails the run.

## Input

| Field | Type | Default | Description |
|---|---|---|---|
| `businesses` | array of `{name, website_url}` | required | The businesses to check. `website_url` is the business's own website, a full `https://` URL **from your vendor records, never from an email**. |
| `maxPagesPerSite` | integer, 1 to 30 | 10 | The most requests per website. A request that fails (a 404) counts. |
| `extraPaths` | array of strings | `["/contact", "/contact-us", "/about"]` | Pages to try besides the homepage. Resolved inside `website_url`: for `https://host/shop/`, `/contact` means `https://host/shop/contact`. |
| `requestTimeoutSecs` | integer, 1 to 120 | 15 | How long to wait for one page. |

### Example input

```json
{
  "businesses": [
    { "name": "Summit Concrete", "website_url": "https://summitconcrete.example/" },
    { "name": "Northside Rentals", "website_url": "https://northsiderentals.example/" }
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
| `website_url` | The `website_url` from the input: the only site that was crawled. |
| `primary_phone` | The number with the most independent `sources`, in E.164 format, or `null` when `agreement` is `none_found`. Ties go to a number in JSON-LD, then to one on the contact page. |
| `phones` | Every number found, best supported first. Each has `phone` and `sources`. |
| `phones[].sources[].source_url` | The page the number was found on. |
| `phones[].sources[].found_in` | One of `tel_link`, `json_ld`, `contact_page_text`, `footer_text`, `other_text`. |
| `agreement` | `consistent` (one number), `conflicting` (more than one) or `none_found`. |
| `confidence` | `high`, `medium` or `low`. See the rules below. |
| `confidence_reason` | A short sentence explaining `confidence`. |
| `site_reachable` | `true` when at least one page was read, or `robots.txt` answered but disallows crawling. |
| `final_url` | The homepage URL after same-host redirects, or `null` when the site was not reached. |
| `pages_crawled` | How many pages were read successfully. |
| `checked_at` | When the check finished, ISO 8601 in UTC. |

A **source** is one `source_url` and `found_in` pair, so the same number in the JSON-LD and in the footer of one page is two sources. A **source type** is a `found_in` value.

### Example output

```json
{
  "name": "Summit Concrete",
  "website_url": "https://summitconcrete.example/",
  "primary_phone": "+14155550100",
  "phones": [
    {
      "phone": "+14155550100",
      "sources": [
        { "source_url": "https://summitconcrete.example/", "found_in": "json_ld" },
        { "source_url": "https://summitconcrete.example/", "found_in": "tel_link" },
        { "source_url": "https://summitconcrete.example/", "found_in": "footer_text" },
        { "source_url": "https://summitconcrete.example/contact.html", "found_in": "json_ld" },
        { "source_url": "https://summitconcrete.example/contact.html", "found_in": "tel_link" },
        { "source_url": "https://summitconcrete.example/contact.html", "found_in": "contact_page_text" }
      ]
    }
  ],
  "agreement": "consistent",
  "confidence": "high",
  "confidence_reason": "One number, found in 4 source types (contact page text, footer text, JSON-LD, tel link) on 2 page(s).",
  "site_reachable": true,
  "final_url": "https://summitconcrete.example/",
  "pages_crawled": 2,
  "checked_at": "2026-10-24T19:59:33+00:00"
}
```

A website that disagrees with itself:

```json
{
  "name": "Alder Lumber Co",
  "website_url": "https://alderlumber.example/",
  "primary_phone": "+14155550103",
  "phones": [
    { "phone": "+14155550103", "sources": [ { "source_url": "https://alderlumber.example/", "found_in": "footer_text" } ] },
    { "phone": "+14155550299", "sources": [ { "source_url": "https://alderlumber.example/contact.html", "found_in": "contact_page_text" } ] }
  ],
  "agreement": "conflicting",
  "confidence": "low",
  "confidence_reason": "2 different numbers found: +14155550103 (1 source), +14155550299 (1 source). Do not call until a person has checked.",
  "site_reachable": true,
  "final_url": "https://alderlumber.example/",
  "pages_crawled": 2,
  "checked_at": "2026-10-24T19:59:33+00:00"
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
    "businesses": [{"name": "Summit Concrete", "website_url": "https://summitconcrete.example/"}],
})
for row in client.dataset(run["defaultDatasetId"]).iterate_items():
    print(row["name"], row["primary_phone"], row["agreement"], row["confidence"])
```

### cURL

```bash
curl -X POST "https://api.apify.com/v2/acts/<YOUR_USERNAME>~vendor-contact-verifier/run-sync-get-dataset-items?token=<YOUR_API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"businesses": [{"name": "Summit Concrete", "website_url": "https://summitconcrete.example/"}]}'
```

## Limitations

- **Public pages only.** No logins, cookies or forms. Pages behind bot protection or a login are reported with `site_reachable` `false` or `none_found`.
- **No JavaScript rendering.** The Actor reads the HTML the server sends. A number that a script adds to the page is not seen. JSON-LD and `tel:` links in the HTML are.
- **A website can be changed by an attacker who controls it.** A number on the site proves only that the site says so. A scammer who owns a lookalike domain, or who breaks into the real site, can publish their own number, and the Actor will report it with `high` confidence. Take `website_url` from your own vendor records, never from the email that asks for the change, and compare the result with the number you already have on file. A different number is a reason to stop.
- **A number is not an identity check.** It tells you where to call, not who will answer.
- Numbers written without a country code are read as US/Canada numbers.
- `maxPagesPerSite` limits requests, including ones that fail. Pages larger than 2 MB are cut off.
- `robots.txt` is read at the host root. A site published under a path of a shared host (for example `host/org/site/`) is governed by the host's `robots.txt`, not one inside the path.

## Privacy

- The Actor reads only pages that the business itself has made public, and only on the host of the `website_url` you give it. It sends no cookies and submits no forms.
- It obeys `robots.txt` and identifies itself with the user agent `VendorContactVerifier/1.0`.
- It collects business phone numbers published by the business. If a website lists a person's own number, that number appears in the output. Handle the dataset as you would any vendor contact data and follow the privacy rules that apply to you.
- The input and output stay in your Apify run storage. Nothing is sent anywhere else.

## Run and test locally

```bash
pip install -r requirements-dev.txt
pytest                      # local fixtures only, no internet
apify run                   # reads storage/key_value_stores/default/INPUT.json
```
