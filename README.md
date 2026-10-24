# Countersign

## Run it locally

Two terminals, both starting at the repo root. Backend and frontend share one `.env` at the repo root.

First time only: `cp .env.example .env`, then in `.env` set:

```
VITE_API_URL=http://localhost:8000
VITE_USE_MOCKS=false
```

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

- Between demos: "Reset demo" in the top bar (or press R) restores the seeded week in under a second (or `curl -X POST http://localhost:8000/api/demo/reset`).
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
