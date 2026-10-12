# plan.md — Telemetry Tracker Implementation Plan

**Status**: M0–M4 complete. M5 pending (driver chat, F1TV access flow, gated live timing).
**Repo**: `telemetry-tracker`
**Companion documents**: `agent.md` (premises and Change Register)

Project using F1 telemetry from FastF1 to extract insights, with an interactive Flask UI, a data/API server, and a natural-language builder agent that generates new analysis screens.

## 1. Goals

- One Flask interface (`app/`) for interactive data review and analysis over F1 FastF1 data.
- One background Flask server (`server/`) retrieving data from FastF1 and normalizing it before sending it to the UI.
- One builder agent (`builder/`) that takes natural-language instructions and generates FastF1 analysis functions plus plotting code. The builder registers them on the server and verifies availability.

## 2. Decisions (confirmed)

| Topic | Decision |
|---|---|
| Builder LLM | OpenAI-compatible client via env config, plus a mock mode so everything works offline |
| Frontend | Jinja2 + vanilla JS + Plotly (CDN), no build step |
| Code safety | AST whitelist validation + subprocess sandbox (time/memory limits) |
| Live Data | Deferred to M5; until then "Live" maps to replay of the latest completed session |
| Built screens | Dedicated page per screen (`/screens/<id>`) + screen list in nav |
| Tooling | uv for env/deps/run; Ruff for lint + format, enforced project-wide |
| Change tracking | Every agent appends changes to `agent.md`'s Change Register |
| Live gating | App must obtain F1TV access (token) before any live-timing attempt |
| Writing style | ASD-STE100 Simplified Technical English for all communication and construction texts (see section 12) |

## 3. Process topology

| Process | Port | Role |
|---|---|---|
| `app/` | 5000 | Flask UI — renders screens, talks only to `server` (and `builder` for build requests) |
| `server/` | 5001 | Flask API — owns FastF1 access, caching, normalization, function registry |
| `builder/` | 5002 | Agent service — NL → FastF1 code → validate → register on server → smoke-test → save screen spec |

## 4. Repository layout

```
telemetry-tracker/
├── agent.md                        # project premises + Change Register
├── plan.md                         # this plan
├── README.md
├── pyproject.toml                  # uv deps + ruff config
├── uv.lock                         # committed
├── .python-version                 # pinned interpreter (3.12)
├── .env.example                    # ports, BUILDER_TOKEN, LLM_*, F1TV_TOKEN
├── run.sh                          # starts all three services via `uv run`
├── data/cache/                     # fastf1.Cache (gitignored)
├── server/
│   ├── app.py                       # Flask API (:5001)
│   ├── config.py                    # env loading and paths
│   ├── session_manager.py           # lazy load + background threads + state machine
│   ├── catalog.py                   # events/sessions/drivers/laps
│   ├── normalize.py                 # timespan & length normalization → envelope
│   ├── analysis.py                  # hand-written seed analyses
│   ├── schemas.py                   # envelope JSON schema
│   ├── sandbox/
│   │   ├── validate.py              # AST whitelist validator (single source of truth)
│   │   └── runner.py                # subprocess entrypoint with rlimits
│   ├── registry/
│   │   ├── __init__.py              # registry store (register/list/run)
│   │   └── generated/               # generated functions: <id>.py + <id>.json (gitignored)
│   └── routes/                      # catalog.py, analysis.py, registry.py, live.py
├── app/
│   ├── app.py                       # Flask UI (:5000)
│   ├── templates/                   # base.html, index.html, screens.html, screen.html
│   └── static/                      # js/{main,charts,timeline}.js, css/style.css
├── builder/
│   ├── app.py                       # Flask service (:5002)
│   ├── agent.py                     # LLM loop: NL → code → validate → register → smoke test
│   ├── llm.py                       # OpenAI-compatible client + mock mode
│   ├── prompts.py                   # strict prompt with allowed-pattern cookbook
│   └── screens/                     # saved screen specs (<id>.json, gitignored)
└── tests/                           # pytest: normalization, validator, registry round-trip
```

## 5. Data contract

Every server/builder function returns one generic envelope so the app stays F1-agnostic:

```json
{
  "kind": "telemetry | trackmap | barchart | gap | image",
  "x": { "name": "distance", "unit": "m", "values": [] },
  "series": [ { "label": "VER · L12", "color": "#3671C6", "values": [] } ],
  "meta": { "track_length_m": 5412 }
}
```

Normalization patterns:

- **Timespan**: interpolate channels onto a fixed time grid. Absolute session time for same-moment streams (positions, gaps); lap-relative time for lap comparisons.
- **Length**: `telemetry.add_distance()`, then grid over `0..track_length` (step ~5 m). Default for qualifying/lap comparisons (two cars/drivers).

## 6. `server/` design

- **SessionManager**: background threads load sessions; state machine `absent → loading → ready | error`. App calls `/api/session/<year>/<round>/<code>/prepare`, then polls `/status`. FastF1 cache enabled at `data/cache` (avoids multi-minute HTTP timeouts).
- **Endpoints**: `/api/events`, `/api/events/<y>/<round>/sessions`, `/drivers`, `/laps?driver=`, `/trackmap`, `/telemetry?...&normalize=timespan|length`, `/compare`.
- **Registry + sandbox**:
  - `POST /api/registry/register` requires `BUILDER_TOKEN`, re-validates AST (never trusts builder), stores source + SHA-256 metadata.
  - `POST /api/registry/<id>/run` executes in a subprocess: `RLIMIT_AS` ~2 GB, CPU + wall timeout, matplotlib `Agg`, sanitized env. Returns envelope or error.
  - No delete endpoint; duplicate/colliding IDs rejected.
- **AST whitelist**: imports limited to `fastf1`, `numpy`, `pandas`, `matplotlib`, `server.normalize`; bans `os`, `sys`, `subprocess`, `socket`, `open`, `exec`, `eval`, `__import__`, dunder attribute access, non-import attribute writes. Violations return 400 + reason (reused as LLM retry feedback).
- **Seed analyses** (hand-written, same envelope): track map, single-driver telemetry (speed/throttle/brake/gear), lap-time bars/gap, 2-car compare with delta.

## 7. `app/` design — main screen

```
┌──────────────────────────┬─────────────────┐
│ Event ▾  Session ▾       │ Drivers         │
│ ┌──────────────────────┐ │ (search, select,│
│ │  Track map (Plotly)  │ │  lap A/B)       │
│ │        center-left   │ │─────────────────│
│ └──────────────────────┘ │ Mini-telemetry  │
│                          │ (right-top)     │
│                          │─────────────────│
│                          │ Driver chat     │
│                          │ (right-bottom)  │
├──────────────────────────┴─────────────────┤
│ Timeline (laps/time → sets lap)            │
│ [Builder instructions ..................]  │
└────────────────────────────────────────────┘
```

- Event dropdown: newest → oldest from `get_event_schedule`; type-to-search (vanilla combobox with `datalist` fallback).
- Session dropdown: FP1–FP3, Sprint Quali, Sprint, Quali, Race; "Live Data" entry (see section 10).
- Compare: driver vs. same driver (2 laps) or driver vs. driver (2 laps), driven by envelope renderers.
- Load states: spinners while a session is `loading`; mini telemetry defaults to selected driver's fastest lap.
- `/screens` list + `/screens/<id>` render builder screens generically (Plotly from envelope, or image output).
- Chat (right-bottom): placeholder in M3, functional in M5 via same LLM client with server data tools.

## 8. `builder/` design

Per instruction: prompt (allowed FastF1 patterns + envelope schema + few-shot examples) → LLM → extract code + screen spec → local AST validation (imports validator from `server.sandbox.validate`) → ruff check → register on server → **smoke-run via server** with current event/session → validate envelope (JSON schema) → save spec to `builder/screens/` → reply with link.

- Failures feed back to the LLM (≤3 retries), then refusal/error message.
- Out-of-scope requests (non-FastF1, destructive) refused at prompt + validator level with canned refusal response.
- Mock mode returns prebuilt known-good analyses so the whole system runs without an API key.
- Screen spec: `{id, title, instruction, created, panels: [{type: "builtin"|"registered", fn, params}]}`.

## 9. Tooling: uv + Ruff

- **uv** owns env/deps:
  - `pyproject.toml` deps: `flask`, `fastf1`, `pandas`, `numpy`, `matplotlib`, `requests`, `python-dotenv`, `openai`, `jsonschema`, `ruff`; dev group: `pytest`.
  - `uv python pin 3.12` (system Python is 3.14; 3.12 avoids FastF1 wheel risk).
  - `uv sync`, `uv run <service>`; `uv.lock` committed.
- **Ruff** enforced project-wide:
  - Config in `pyproject.toml`: line-length 100; rules `E, F, I, UP, B, SIM, S`; generated code excluded from the project check and checked separately at build time.
  - Standard checks: `uv run ruff check .` and `uv run ruff format --check .`.
  - **Builder gate**: candidate generated functions must pass ruff before registration; failures become LLM retry feedback.
  - Optional pre-commit hook running ruff + ruff-format.

## 10. F1TV gate for live timing (M5)

1. User selects **Live Data** → app calls `GET /api/live/status`.
2. No credentials → app shows **F1TV access modal** (F1TV token input + instructions; F1TV Pro required per FastF1 live-timing auth). Token masked, never logged.
3. Submit → `POST /api/live/auth`; server validates against FastF1's live-timing auth (pinned to installed fastf1 version) and only then starts capture via `fastf1.livetiming` (cache enabled).
4. Auth failure or outside live window → structured error; app falls back to replay of latest session.
5. Server refuses live endpoints without valid credentials; token in memory only, optional `.env` persist (`F1TV_TOKEN=`, gitignored) on user opt-in.

## 11. `agent.md` — premises + Change Register

`agent.md` = project premises **+ living Change Register**. Every agent that modifies the project (including the Builder service) appends an entry on any change. Coding agents run ruff and pytest before they log. The builder appends audit entries whenever it registers a function or saves a screen.

## 12. Writing and construction standards (ASD-STE100)

All texts in this project follow ASD-STE100 Simplified Technical English: agent replies, documents, comments, docstrings, UI texts, commit messages, and Change Register entries.

- Short sentences. Maximum 20 words for a step. Maximum 25 words for a description.
- Active voice. Imperative for instructions.
- One word for one meaning.
- No idioms, humor, or metaphors. No contractions.
- Lists for steps and items. One instruction per sentence.
- Keep technical nouns as they are.

## 13. Milestones

| # | Deliverable | Status |
|---|---|---|
| M0 | uv/ruff scaffolding: `pyproject.toml` (pinned 3.12), `.env.example`, `agent.md`, `plan.md`, README, `run.sh`; verify fastf1 syncs under uv | done |
| M1 | Server catalog (events/sessions/drivers/laps) + SessionManager + caching + tests | done |
| M2 | Normalization module (timespan + length) + seed analyses + registry/sandbox + ruff gate + tests | done |
| M3 | App main screen fully interactive (all panels, compare, timeline, builder box wired; chat placeholder) | done |
| M4 | Builder agent end-to-end (mock + LLM) + `/screens` pages + refusal behavior tests | done |
| M5 | Driver chat functional; F1TV access flow + gated live timing; extra channels; polish | pending |

## 14. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Python 3.14 wheels for fastf1/pandas | uv-pinned 3.12 interpreter |
| Slow first session load | Background loading + status polling, on-disk fastf1 cache |
| LLM code quality | Cookbook prompt + smoke test + ruff gate + ≤3 retries |
| FastF1 API drift | Pin versions in `uv.lock`; isolate fastf1 calls in `server/` |
| Generated code abuse | AST whitelist (builder + server re-check) + subprocess rlimits + token auth |

## 15. Open items

- Live: the real `/api/live/*` auth calls will be finalized against the installed FastF1 version in M5.
