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

Open http://localhost:5173.

### At the venue

- Between demos: "Reset demo" in the top bar restores the seeded week in under a second (or `curl -X POST http://localhost:8000/api/demo/reset`).
- Leaderboard on the TV: http://localhost:5173/leaderboard?tv=1
- Vite reads `.env` only when it starts: restart `npm run dev` after changing a `VITE_` value.
- Stopping the backend: Ctrl+C. An open board keeps its event stream open, so if uvicorn waits for connections to close, press Ctrl+C again.
- No backend available: set `VITE_USE_MOCKS=true` and run only the frontend.
- `uv` is not on your PATH (it was installed without editing shell profiles). If `~/.local/bin/uv` is missing, reinstall it with `curl -LsSf https://astral.sh/uv/install.sh | sh`.
