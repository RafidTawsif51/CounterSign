# Countersign

## CRS integration

Countersign uses the CRS sandbox to decide whether a confirmed phone call may move money. Before the voice agent dials a vendor, three real CRS checks run at once (`backend/app/services/identity.py`, called from `verify.py`). With `MOCK_CRS=true` the old deterministic mock is used and nothing below runs.

### Products used (only these three)

| Check | CRS product | Question it answers |
|---|---|---|
| Reverse phone | Accurate Append `POST /accurate-append/reverse` | Does the number we are about to call belong to the vendor's known contact? |
| Email risk | AtData Fraud Finder `POST /fraud-finder/fraud-finder` | Is the party that asked for the bank change risky? (score under 30 pass, 30 to 59 review, 60 and up fail) |
| Identity | TransUnion identity verification (basic) `POST /transunion/identity-manager-verification/basic` | Is the owner or contact (or whoever stands behind the request) a verified identity? (SSN or birth date not matching the name fails; an address-only mismatch is review) |

We deliberately do not call credit report, criminal, eviction or bankruptcy endpoints. Paying an invoice does not need a person's credit or court history, we have no permissible purpose for it, and holding less data is safer. Minimum necessary data.

### How it changes the decision

1. Reverse phone fails: that number is not dialed. The next independent number is tried; if none passes, nothing is dialed and the payment is held for the controller.
2. Email risk or identity fails: the reasons are added to the hold reasons, and the call still happens (the call is the out-of-band proof).
3. A confirmed call releases the payment only if the CRS status is `pass`. On `review`, `fail` or `CRS unavailable` the payment stays held for the controller with the CRS findings in the reasons. A denied call blocks, whatever CRS said.
4. If CRS cannot be reached or times out (8 s per request) it is recorded as "CRS unavailable" and treated like `review`. It is never a silent pass.

The summary of every check is written to the audit log (`crs_identity_check`) and shown on `GET /api/vendors/{vendor_id}/identity`, which keeps two subjects apart so a vendor is never marked down for an attacker's request:

```
{
  "status": "pass",                       // the vendor's own status (kept for older clients)
  "vendor": {                             // the vendor's own standing
    "status", "summary", "persona", "checked_at",
    "checks": [reverse_phone, owner identity check]
  },
  "latest_request": {                     // the newest bank-change request, or null
    "status", "summary", "persona", "requested_by_domain", "payment_id", "checked_at",
    "checks": [fraud_finder on the requester, requester identity check]
  }
}
```

Summaries name their subject, for example `vendor Summit Concrete clear (2/2 checks passed)` and `request from summit-concrete.co flagged: fraud finder: email risk score 88; ...`. Hold reasons for request checks end with `(request from <domain>)`. The release rule still looks at both: a confirmed call pays only if the vendor and the request are all clear. No PII appears in either section.

### Sandbox test identities (read this)

The CRS sandbox only returns meaningful data for its published test personas, so our fictional data is mapped onto them (`SANDBOX_PERSONAS` in `identity.py`):

| Our data | CRS persona |
|---|---|
| Summit Concrete's owner and contact | P19 Grace Nakamura (small-business owner, approve) |
| Every other demo vendor | P01, P02 or P19 (approve), chosen stably by vendor id |
| A request from an address outside the vendor's domain (the seeded attacker, any lookalike) | P13 Kayla Brennan (synthetic identity, fraud) |
| Same, when the Reply-To differs from the sender | P12 Victor Anand (identity mismatch) |

CRS lookups use the mapped persona's data. The number we actually dial is still our `DEMO_VENDOR_PHONE`; the reverse lookup asks CRS about the persona's phone, not that number. The persona choice uses only the sender address, never an "is attack" label.

### Data minimization and responsible use

- Only summaries are stored: check name, pass, review or fail, risk score, short reason strings and the CRS request id. No SSN, birth date, address or raw response is stored, returned or logged. Persona details live in code only because the sandbox needs them to answer, and they are CRS's own fake test data.
- Tokens and passwords are never logged. Credentials come from `CRS_USERNAME` and `CRS_PASSWORD` in the environment (or `.env`).
- Results are cached for 10 minutes per check and subject, so one run makes at most a handful of live requests.

### Try it

```
cd backend
python -m scripts.integrations_cli smoke-crs
python -m scripts.integrations_cli create-test-hold --legit    # request from the vendor's real domain: CRS passes
python -m scripts.integrations_cli create-test-hold            # request from a lookalike domain: CRS fails
```

### Known limits

- The sandbox responds per test persona, so a real phone number is never actually looked up. The reverse-phone fail path is proven by tests and by the attacker persona.
- TransUnion basic returns the same risk indicator for every test persona; the decision uses its alert messages and match fields, which do differ.
- The pass and fail thresholds are starting points, not validated. The refresh-token endpoint rejects tokens that are not near expiry, so the client normally re-logs in on a 401.
- Rate limit seen in response headers: 80 requests per window; the cache and a single shared token keep a run well under it.
