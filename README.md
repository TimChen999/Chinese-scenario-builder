# Scenarios App

Generates **authentic** real-world Chinese reading scenarios on demand. Combines a FastAPI backend (image search → vision OCR → scenario assembly via Gemini) with a React/TypeScript frontend, and composes with the Pinyin Tool browser extension via shared DOM (the extension augments selected text with pinyin overlays).

See [`DESIGN.md`](DESIGN.md) for the full architecture and decision record.

---

## Architecture at a glance

| Component | Stack | Port |
|---|---|---|
| Backend  | Python 3.11+, FastAPI, SQLAlchemy 2 (async), SQLite, Gemini, SerpAPI | `8000` |
| Frontend | React 18, TypeScript 5, Vite 5, Tailwind 3, TanStack Query 5      | `5173` |
| Extension | Existing **Pinyin Tool** browser extension (untouched)              | n/a    |

The three loosely-coupled systems each own one slice of responsibility (DESIGN.md §1). The app does NOT know the extension exists; the extension does NOT know the app exists. They co-exist in the browser.

---

## Quick start (one click)

Double-click [`start.bat`](start.bat). On first run it:

1. Creates the Python venv and installs backend deps (~2 min)
2. Copies `backend/.env.example` to `backend/.env` (you must edit it
   to add `GEMINI_API_KEY` and `SERPAPI_KEY` before generating
   scenarios)
3. Applies database migrations
4. Installs frontend deps (~1 min)
5. Spawns both servers in their own windows and opens
   [http://localhost:5173](http://localhost:5173)

Subsequent launches skip every bootstrap step that's already done
(typical launch < 5 s). Stop each server with `Ctrl+C` in its window.

The manual setup steps below are still available if you'd rather
drive it yourself.

---

## Prerequisites

- **Python 3.11+** (this repo was developed against 3.13). The system `python` may be 3.10; on Windows, prefer the launcher: `py -3.13`.
- **Node 18+** (developed against `node v24` + `npm 11`).
- A **Google Gemini API key** (the same one the Pinyin Tool extension uses; one key powers both).
- A **SerpAPI key** for Google Images search (free tier: 100/mo).

---

## Local setup

### 1. Backend

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.example .env
# Edit .env -- fill in GEMINI_API_KEY and SERPAPI_KEY
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

The backend boots on `http://127.0.0.1:8000`. Try:

- `GET http://localhost:8000/healthz` → `{"status":"ok"}`
- `GET http://localhost:8000/docs` → interactive Swagger UI

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

The app boots on `http://localhost:5173`. Vite proxies `/api/*` → `http://localhost:8000/*`.

### 3. Extension

Install the **Pinyin Tool** browser extension (lives at the sibling
`Du Chinese Plugin/` folder, untouched by this repo). With it
installed and enabled, selecting Chinese text on any of the scenarios
app's pages should reveal the pinyin overlay.

---

## Tests

### Backend

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/unit tests/integration       # 49 fast tests
.\.venv\Scripts\python.exe -m ruff check .                               # lint
```

Live tests cost real money and require API keys. They are **off by
default**:

```powershell
$env:RUN_LIVE_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest tests/live
```

The vision-live tests need real photos in
`backend/tests/fixtures/images/` (see that folder's README for
sourcing criteria). Without real photos they self-skip.

### Frontend

```powershell
cd frontend
npm test            # 42 tests, full suite
npm run lint        # tsc --noEmit
```

---

## Project layout

```
Chinese Scenarios App/
├── DESIGN.md                          # design doc (§1-13)
├── README.md                          # this file
├── .gitignore
├── backend/
│   ├── pyproject.toml                 # deps + pytest + ruff
│   ├── .env.example
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/0001_initial.py   # 4 tables
│   ├── app/
│   │   ├── main.py                    # FastAPI factory + routers
│   │   ├── core/                      # config, prompts
│   │   ├── db/                        # base, session, models
│   │   ├── schemas/                   # HTTP request/response
│   │   ├── agent/                     # search, vision, filter, assembly, orchestrator
│   │   ├── api/                       # scenarios, jobs, tasks, history, images
│   │   └── services/                  # job_runner, image_store
│   └── tests/
│       ├── unit/                      # 32 tests (pure modules)
│       ├── integration/               # 19 tests (API end-to-end with in-memory DB)
│       ├── live/                      # gated by RUN_LIVE_TESTS=1
│       └── fixtures/
│           ├── api_responses/         # SerpAPI / Gemini sample JSON
│           └── images/                # placeholder JPGs + README
└── frontend/
    ├── package.json
    ├── vite.config.ts                 # /api proxy + vitest setup
    ├── tailwind.config.js
    ├── src/
    │   ├── main.tsx                   # React root
    │   ├── App.tsx                    # router
    │   ├── api/                       # client, schemas, scenarios, jobs, history
    │   ├── hooks/                     # TanStack hooks + useJobStream + useIsDesktop
    │   ├── components/                # Layout, Nav, RawContent, TaskItem, ...
    │   └── pages/                     # Library, Generate, Scenario, History
    └── tests/
        ├── App.test.tsx
        ├── api/client.test.ts
        ├── components/
        ├── pages/
        └── mocks/                     # MSW server + EventSource mock
```

---

## Composition with the Pinyin Tool extension

The scenarios app adheres to the constraints in DESIGN.md §9 so the
extension's selection-driven pinyin overlay works unchanged:

- `raw_content` is rendered via `<RawContent>` -> `<pre lang="zh"
  data-scenario-content="raw">` with `whitespace-pre-wrap`. No
  `contenteditable`, no SVG `<text>`, no `user-select: none`.
- No `mouseup` / `mousedown` handlers (and no `stopPropagation`)
  on any ancestor of `raw_content` or `scene_setup` -- the
  extension listens on `document` and a local stop would break it.
- Distinct CSS class prefix: every scenarios-app class starts with
  `scenario-` (or is a Tailwind utility); none start with `hg-`,
  the extension's overlay prefix. The extension's host element id
  is `hg-extension-root`; we never use that id either.

---

## Manual end-to-end checklist (DESIGN.md Step 13)

Run after each substantive change. Backend on `:8000`, frontend on
`:5173`, extension installed and enabled.

1. Visit `http://localhost:5173/` — Library shows empty state.
2. Click "Generate a scenario", enter "ordering breakfast at a Beijing 早餐店".
3. Click Generate. Watch progress: queries → search → filter → ocr → assembly → done.
4. Auto-redirected to scenario page.
5. Verify image loads on left, scene_setup + raw_content in center, 3 tasks on right.
6. Read raw_content: select 3 characters. Confirm extension overlay appears with pinyin.
7. Right-click a selection → context menu entry from extension visible.
8. Type an answer for task 1. Submit. Verify result (correct or wrong with explanation).
9. Submit answers for all 3 tasks.
10. Verify score footer shows correct count.
11. Navigate to `/history`. Verify the 3 attempts appear, with correct/incorrect status.
12. Filter by Incorrect. Verify only incorrect ones show.
13. Click an attempt, verify scenario page reloads.
14. Navigate to `/`. Verify the new scenario appears in library.
15. Generate a second scenario. Verify it appears in library and history works across both.
16. Restart backend. Re-visit pages. Verify all data still present.
17. Disable extension. Re-visit scenario page. Verify the app works (no JS errors), just no pinyin overlay.

---

## Troubleshooting

- **`No suitable Python runtime found` from `py`**
  Install Python 3.11+ from python.org or the Microsoft Store. The
  command `py -0` lists detected interpreters.

- **`alembic upgrade head` fails with "unable to open database file"**
  Ensure `backend/data/` is writable. The Alembic env.py creates it
  on demand, but may fail in a read-only working directory.

- **MSW logs "intercepted a request without a matching request handler"
  during frontend tests**
  Add a default handler in the test or `tests/mocks/handlers.ts`. We
  use `onUnhandledRequest: "error"` to surface fetch typos.

- **`SearchError: SERPAPI_KEY is not configured`**
  Confirm `backend/.env` has the key set and the backend has been
  restarted (pydantic-settings caches the values at first read).

- **Pinyin overlay does not appear on raw_content**
  Confirm the Pinyin Tool extension is installed and enabled on
  `localhost`. The extension matches `<all_urls>` so no per-site
  permission is needed. Inspect the page in DevTools and confirm
  the `<pre>` carries `lang="zh"` and `data-scenario-content="raw"`.

---

## Configuration

See [`backend/.env.example`](backend/.env.example) for every supported
env var. None are logged by the app.

| Variable | Required | Default |
|---|---|---|
| `GEMINI_API_KEY`     | yes (for any LLM call) | `""` |
| `SERPAPI_KEY`        | yes (for image search) | `""` |
| `DATABASE_URL`       | no | `sqlite+aiosqlite:///./data/scenarios.db` |
| `IMAGE_STORAGE_DIR`  | no | `./data/images` |
| `ALLOWED_ORIGINS`    | no | `http://localhost:5173` |
| `LOG_LEVEL`          | no | `INFO` |
| `RUN_LIVE_TESTS`     | no (test gate) | unset |
