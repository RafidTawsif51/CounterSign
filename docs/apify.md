# Apify: Vendor Contact Verifier

**Actor:** Vendor Contact Verifier, by `earnest_grill` on Apify (Actor ID `qq1lty7RcS9G6yFfc`, version 0.2).
**Store link:** https://apify.com/earnest_grill/vendor-contact-verifier (works once the Actor is public; until then the Console page is https://console.apify.com/actors/qq1lty7RcS9G6yFfc).
**Source:** `apify/vendor-contact-verifier/` in this repository. **Prize track:** Apify, and Best Actor.

## What it does

Before an accounts payable team calls a vendor to confirm a bank change, the Actor finds the vendor's real phone number on the vendor's own public website, with proof of where it came from. For each business it crawls `website_url` (homepage, `/contact`, `/contact-us`, `/about` and links found on those pages), reads phone numbers from `tel:` links, schema.org JSON-LD and visible text, normalizes them to E.164 and returns one row per business: `primary_phone`, every number with its `sources` (`source_url` and `found_in`), `agreement` (`consistent`, `conflicting`, `none_found`), `confidence` (`high`, `medium`, `low`) and a `confidence_reason`.

It reads only the host and folder of the `website_url`, obeys `robots.txt`, never follows links to other hosts or to a neighbour's folder, and ignores numbers in scripts, forms and hidden elements.

## What it does in Countersign

Countersign's core rule is that money never goes to a new destination without proof from outside the channel that asked for it. The verification call is that proof, and it only works if the number we dial does not come from the email asking for the change (the scammer's email will carry the scammer's number).

The Actor is the independent-number step of every verification call (`MOCK_APIFY=false`):

1. A payment is held because its destination account changed, and `services/verify.py` prepares the verification call.
2. `services/contacts.py` runs the Actor for that one vendor with the vendor's `website_url` from our vendor record. Nothing from the request email or invoice (no URL, domain or phone) is ever an input. The whole lookup has a 20 second limit, and the result is cached for one hour per vendor.
3. `verify.py` applies the spec's number rule to the Actor's `primary_phone` and the most recently verified on-file contact:

| Result | The call goes to | Recorded |
|---|---|---|
| They match | that number, with source `website` and the Actor's `source_url` as proof | the website contact is stored or updated in `vendor_contacts` with `source_url` and `last_verified` |
| They differ | the number verified longest ago (the on-file one) | hold reason `contact sources disagree`, with an `evidence_id` that `/ask` can cite; the website's number is stored but not dialed |
| `confidence` `low`, or `agreement` `none_found` or `conflicting` | the on-file number | hold reason `independent contact check found no usable number` |
| Apify fails or times out | the on-file number | hold reason `independent contact check unavailable`; `/api/system/status` shows Apify as degraded until a lookup works again |

A failure of the independent check never moves money and never removes a hold: it only changes why the call went where it did. Every check writes audit rows (`independent_contact_checked` on the payment, `contact_recorded` on the contact), and only `verify.py` writes `vendor_contacts`; the payment agent has no function that does.

What the controller sees: `GET /api/payments/{id}` returns `independent_contact` (provider "Apify Vendor Contact Verifier", `source_url`, `confidence`, `agreement`, `sources_agree`, `hold_reasons`, `evidence_id`). `call.started` carries the same `source_url`, `confidence`, `agreement` and `hold_reasons` next to `contact_source`. Payment detail and the live call card say "Number found by Apify Vendor Contact Verifier" with the source URL as a link. Asked "where did you get this number?", `/ask` answers from that evidence and cites it.

## How we call it

From the backend (`backend/app/services/contacts.py`), with `apify-client`. `APIFY_TOKEN` and `APIFY_ACTOR_ID` come from settings and are never logged or stored:

```python
client = ApifyClientAsync(settings.apify_token)
run = await client.actor(settings.apify_actor_id).start(
    run_input={"businesses": [{"name": vendor.name, "website_url": vendor.website_url}], "maxPagesPerSite": 6, "requestTimeoutSecs": 6},
    run_timeout=timedelta(seconds=15),
)
finished = await client.run(run.id).wait_for_finish(wait_duration=timedelta(seconds=18))
row = (await client.dataset(finished.default_dataset_id).list_items(limit=1)).items[0]
```

The row is data from a website, so it is checked before use: `primary_phone` must be E.164, `agreement` and `confidence` must be known values, and the proof `source_url` must be a page of the vendor's own `website_url` (same host, inside its folder). A row that fails any check is not a number.

`python -m scripts.warm_cache` runs the lookup for Summit Concrete and the server does the same at start (with `MOCK_APIFY=false`), so the first demo call does not wait for the Actor. The cache lasts an hour.

### Demo routing

The hosted sites show fictional 555 numbers only. `DEMO_CALL_ROUTES=+14155550100=+1XXXXXXXXXX` (comma separated pairs) swaps a verified number for a team phone at dial time and nowhere else: verification, evidence, `/ask`, payment detail and events all show the fictional number. The routed number must be on `ALLOWED_CALL_NUMBERS` too, or the call is refused. Each routed call writes the audit row "demo routing: call delivered to team phone" (nothing of the team phone is written), and `/api/system/status` shows "Demo: calls routed to team phone".

## Demo data

Our vendors are fictional, and their email domains (for example `summitconcrete.com`) may belong to real businesses, so the Actor must never crawl them. Each vendor has a separate `website_url` on pages we host on GitHub Pages: `https://aayushswami123.github.io/Countersign/<vendor-slug>/` (see `docs/sites.md`). All phone numbers are fictional 555 numbers.

A cloud run on 24 October 2026 (run `ED6WlLx1T57HOiSBJ`, 3 seconds, about $0.00025) returned:

| Business | primary_phone | agreement | confidence |
|---|---|---|---|
| Summit Concrete | +14155550100 | consistent | high |
| Alder Lumber Co (footer and contact page differ) | +14155550103 | conflicting | low |
| Redwood Paint and Coatings (no phone) | none | none_found | low |
| Haulaway Dumpster Service (no contact page) | +14155550130 | consistent | high |
| Summit Concrete attacker lookalike site | +14155550166 | consistent | high |
| A website that does not exist | none | none_found | low (`site_reachable` is `false`) |

The attacker row is the point of the last limitation below: the Actor reports what a site says.

## Limitations

- **Public pages only, no JavaScript rendering.** A number added by a script is not seen. Pages behind a login or bot protection come back as `none_found` or `site_reachable` `false`.
- **A website can be changed by an attacker who controls it.** A scammer who owns a lookalike domain publishes their own number, and the Actor reports it with `high` confidence (see the attacker row above). That is why `website_url` must come from our own vendor record, set before any change request, and why the result is compared with the number on file. A different number is a reason to stop, not a reason to call it.
- **It finds where to call, not who will answer.** It is not an identity check.
- **The crawl stays inside the folder of `website_url`.** Many fictional vendors share one host, so the Actor never wanders into another vendor's folder. It cannot tell whether a folder really belongs to the business.
- Numbers without a country code are read as US/Canada. `maxPagesPerSite` limits requests, including failed ones.
- The vendors and their websites are simulated for the demo. The Actor and the cloud runs are real.

## Publishing checklist

The Actor is private until it is published. Steps are in the Apify Console under the Actor: Publication, then Publish to Store. Before that, set an icon, check the Store title and description (below) and pick the pricing model (pay per usage is the default).

Store description (under 200 characters):

> Find a vendor's real phone number on its own website, with proof of where it came from. Call a number that is not from the email before you confirm a bank change. Built for payment fraud callbacks.
