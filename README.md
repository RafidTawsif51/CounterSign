# Countersign

## Run it locally

Two terminals, both starting at the repo root. Backend and frontend share one `.env` at the repo root.

First time only: `cp .env.example .env`, then in `.env` set:

```
VITE_API_URL=http://localhost:8000
VITE_USE_MOCKS=false
```

Also set `ADMIN_KEY` in `.env` to any long random value. Reset demo, Present and the red-team run need it (the app asks for it once per tab); while it is blank those routes answer 403.

### Backend (port 8000)

```sh
cd backend
~/.local/bin/uv venv --python 3.11 .venv                                    # first time only
~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt   # first time, and after requirements.txt changes
.venv/bin/python seed/seed.py                                               # first time: builds countersign.db (about 4 s)
.venv/bin/uvicorn app.main:app --port 8000
```

Check it: `curl http://localhost:8000/api/health` should print `"status":"ok"` and the mock flags.

### Frontend (port 5173)

```sh
cd frontend
npm install    # first time, and after package.json changes
npm run dev
```

Open http://localhost:5173. Screens, modes and shortcuts are under [Frontend](#frontend).

### At the venue

- Between demos: "Reset demo" in the top bar (or press R) restores the seeded week in under a second (or `curl -X POST -H "X-Admin-Key: $ADMIN_KEY" http://localhost:8000/api/demo/reset`). Reset, Present and the red-team run need `ADMIN_KEY` from `.env`: the app asks for it once per tab and keeps it in that tab's session storage only. With `ADMIN_KEY` blank those routes stay locked.
- Leaderboard on the TV: http://localhost:5173/leaderboard?tv=1, or press L for a separate window to drag onto the second screen.
- On the projector: press F for presentation mode.
- Vite reads `.env` only when it starts: restart `npm run dev` after changing a `VITE_` value.
- Stopping the backend: Ctrl+C. An open board keeps its event stream open, so if uvicorn waits for connections to close, press Ctrl+C again.
- Backend gone mid-demo (Wi-Fi dropped, server crashed): after 5 seconds a line under the top bar offers "Switch to offline demo". See [Live and offline demo](#live-and-offline-demo).
- No backend at all: set `VITE_USE_MOCKS=true` and run only the frontend.
- `uv` is not on your PATH (it was installed without editing shell profiles). If `~/.local/bin/uv` is missing, reinstall it with `curl -LsSf https://astral.sh/uv/install.sh | sh`.

## Frontend

React, Vite and TypeScript with Tailwind CSS, in `frontend/`. `frontend/DESIGN.md` is the design system every screen follows; `/design-check` renders its tokens (a hidden route).

### Screens

| Route | Screen |
|---|---|
| `/` | Payment run: this week's 40 invoices as a ledger, live as the agent pays, holds or blocks each one, with the agent's activity and verification calls beside it |
| `/payments/:id` | Payment detail drawer: why it was paid, held or blocked, the evidence, the verification call, "Ask about this payment", the audit trail, and approve or reject for held payments |
| `/inbox` | AP inbox: vendor threads, lookalike domains and Reply-To mismatches marked inline, invoice preview with "Reveal hidden content" |
| `/attack` | Attack console: pick an attack card or write your own; the result plays out on the board |
| `/leaderboard` | Rob Countersign leaderboard for the second screen, always dark; `?tv=1` for the TV |
| `/red-team` | Red-team results: catch rate by attack family, baseline agent against Countersign |
| `/status` | System status: what is real, sandboxed or simulated, and how we know |

### Run and build

```sh
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build      # type-checks, then builds to dist/ with no warnings
npm run preview    # serves dist/ locally
```

The backend allows `http://localhost:5173` (plus `FRONTEND_URL`) for CORS, so keep the dev server on that port when talking to a local backend.

### Live and offline demo

- **Live** (`VITE_USE_MOCKS=false`): every request goes to `VITE_API_URL`, and the board follows the server's event stream.
- **Offline demo** (mock mode): every request and the event stream are answered in the browser by `src/lib/mock`, on the same fictional Ridgeline Builders data. Nothing reaches the server, no calls are placed and no money moves. Start in it with `VITE_USE_MOCKS=true`.

You can also switch while the app is running, without a reload:

- In live mode the app checks `/api/health` every 2 seconds, and at once whenever a request or the event stream fails. When the server has not answered for 5 seconds, a line under the top bar offers "Switch to offline demo". A run in progress restarts from the top on built-in data. "Keep waiting" hides the line until the next outage.
- While offline, the top bar says "Offline demo". Once the server answers again, "Back to live" appears beside it. A build made with `VITE_USE_MOCKS=true` is offline on purpose: it never checks the server and has no way back.
- A leaderboard window opened with L follows the switch either way.
- Every script loads up front (no lazy routes), so the offline demo keeps working with the Wi-Fi off once the page is open.

### Demo shortcuts

Press ? in the app for this list. Single keys do nothing while you type in a field, and only F and ? work while a dialog or the payment drawer is open.

| Key | Does |
|---|---|
| S | Start the payment run |
| R | Reset the demo, after you confirm |
| A | Open the attack console |
| L | Open the leaderboard in a new window |
| F | Presentation mode: hides the sidebar and scales everything 1.15x; F again to leave |
| ? | Show the shortcuts |
| ⌘K or Ctrl+K | Search pages, vendors and payments |
| G, then P, I, A, L, T or S | Go to payment run, inbox, attack console, leaderboard, red team or system status |

### Credits

- [shadcn/ui](https://ui.shadcn.com) and [Radix](https://www.radix-ui.com): UI primitives, restyled to `DESIGN.md`
- [Recharts](https://recharts.org): the red-team chart
- [Lucide](https://lucide.dev): icons
- [21st.dev](https://21st.dev): `21st review`, the UI checks we ran on every screen during design QA
- [IBM Plex Sans and Mono](https://github.com/IBM/plex), via Fontsource

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
