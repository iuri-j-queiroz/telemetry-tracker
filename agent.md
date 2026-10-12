# agent.md — Project Premises and Change Register

This file is the source of truth for all agents that work on this project.
Read this file first. Then read `plan.md` for the plan and the build status.
Register every change in the Change Register at the end of this file.

## 1. What this project is

Telemetry Tracker is an interface to review and analyze Formula 1 data from the FastF1 Python API.
The system has three services. The services work together.

## 2. Services and their rules

| Service | Port | Job |
|---|---|---|
| `server/` | 5001 | Retrieve data from FastF1. Normalize the data. Hold the function registry. Run registered functions in a sandbox. |
| `app/` | 5000 | Show data to the user. Collect user requests. Talk only to the server and the builder. |
| `builder/` | 5002 | Turn natural-language instructions into FastF1 analysis functions and screens. Register the functions on the server. |

### server rules

- Use only the FastF1 Python API for data. You may use numpy, pandas, and matplotlib for processing and plotting.
- Refuse instructions that are not about FastF1 data.
- Refuse destructive functions. No file deletes, no system access, no network calls outside FastF1.
- Never trust the builder. Validate every function again before registration.
- Run registered functions in a subprocess with time and memory limits.

### app rules

- Keep the app simple. The app does not import FastF1.
- Send all data requests to the server.
- Send builder instructions to the builder service.

### builder rules

- Build only FastF1 data analysis functions and their plots. Refuse all other requests. No exceptions.
- Register each function on the server and smoke-test it before the screen becomes available.
- Pass each candidate through this gate, in this order: AST validation, ruff check, server re-validation, smoke test.

## 3. Data contract — the envelope

Every server function and every registered function returns one JSON envelope.
The app renders the envelope and does not know FastF1 details.

```json
{
  "kind": "telemetry | trackmap | barchart | gap | image",
  "x": { "name": "distance", "unit": "m", "values": [0, 5, 10] },
  "series": [
    { "label": "VER · L12", "color": "#3671C6", "values": [1.0, 2.0] }
  ],
  "meta": { "track_length_m": 5412 }
}
```

- `x` is optional. Track maps put `x` and `y` arrays inside each series item.
- `kind: "image"` returns `"data_base64"` and `"mime"` instead of `series`.
- `meta` holds small extras. Use it for labels and units.

## 4. Normalization patterns

The server normalizes data with two patterns:

- **Timespan**: put all channels on one time grid. Use session time for streams at the same moment (positions, gaps). Use lap-relative time for lap comparisons. Sample step: 0.1 s for laps, 0.5 s for sessions.
- **Length**: use the track length. Call `telemetry.add_distance()` and put all channels on one distance grid from 0 to `track_length`. Sample step: 5 m. This is the default for comparisons of two cars or two laps.

## 5. Safety invariants

- The AST validator in `server/sandbox/validate.py` is the single source of truth. The builder imports it. The server runs it again.
- Allowed imports: `fastf1`, `numpy`, `pandas`, `matplotlib`, and `server.normalize`.
- Banned: file access, `os`, `sys`, `subprocess`, `socket`, `exec`, `eval`, `open`, dunder access, attribute writes, and module-level calls.
- Registered functions use one entry point: `def build(context): ...` and return one envelope.
- `context` has `session` (a loaded FastF1 session or None) and `params` (a dict).
- The server refuses registrations without the `BUILDER_TOKEN`.
- The server runs each function in a subprocess with a wall timeout, CPU limit, and ~2 GB memory limit.

## 6. Writing and construction standard — ASD-STE100

All texts follow ASD-STE100 Simplified Technical English.
This rule applies to:

- Agent replies and status reports.
- Documents: this file, `plan.md`, `README.md`, docstrings, and comments.
- UI texts: labels, buttons, messages, and errors.
- Commit messages and Change Register entries.
- Comments in generated code.

Rules:

- Use short sentences. Maximum 20 words for a step. Maximum 25 words for a description.
- Use the active voice. Use the imperative for instructions.
- Use one word for one meaning. Use the same word for the same thing.
- Do not use idioms, humor, or metaphors. Do not use contractions.
- Use lists for steps and items. One instruction per sentence.
- Keep technical nouns as they are: envelope, lap, stint, telemetry, compound.

## 7. How to run and check the project

```bash
uv sync                          # install everything
uv run python -m server.app     # data server  :5001
uv run python -m app.app        # user interface :5000
uv run python -m builder.app    # builder agent  :5002
./run.sh                         # start all three services
uv run pytest -q                 # tests
uv run ruff check .              # lint
uv run ruff format --check .     # format check
```

## 8. Change Register rules

Register every change in section 9. Use this format:

```markdown
### [YYYY-MM-DD] <component> — <short title>
- **Files**: <files>
- **Change**: <what and why>
- **Checks**: <commands that passed>
- **Decisions/notes**: <what future agents must know>
```

- Coding agents run ruff and pytest before they log.
- The builder appends an audit entry when it registers a function or saves a screen.
- Never delete an entry. Add a new entry when you change or revert an old change.

## 9. Change Register

(the first entries appear below)

### [2026-10-12] project — M0 scaffolding with uv and Ruff

- **Files**: pyproject.toml, .python-version, .env.example, agent.md, plan.md, README.md, run.sh, .pre-commit-config.yaml, .gitignore
- **Change**: Set up the project with uv. Pinned CPython 3.12. Added dependencies and dev dependencies. Added Ruff rules E, F, I, UP, B, SIM, S.
- **Checks**: uv sync; uv run ruff check .; uv run pytest -q
- **Decisions/notes**: The system Python is 3.14. FastF1 can fail there, so the project pins 3.12. Ruff is a main dependency because the builder runs the ruff gate at runtime. Generated code and screen specs are gitignored runtime artifacts.

### [2026-10-12] server — M1 catalog and session manager

- **Files**: server/app.py, server/config.py, server/catalog.py, server/session_manager.py, server/routes/catalog.py
- **Change**: Added the calendar, session details, driver list, and lap list. Sessions load in background threads. The app polls the status route.
- **Checks**: ruff; pytest; live test against Singapore 2026 Qualifying
- **Decisions/notes**: fastf1 3.8.3 has no Season column. Use the Utc session date for the completed flag. Import fastf1.plotting explicitly. The cache lives in data/cache/.

### [2026-10-12] server — M2 normalization, seed analyses, sandbox and registry

- **Files**: server/normalize.py, server/analysis.py, server/schemas.py, server/sandbox/validate.py, server/sandbox/runner.py, server/registry/__init__.py, server/routes/analysis.py, server/routes/registry.py
- **Change**: Added the two normalization patterns (timespan, length). Added the seed analyses: track map, telemetry, compare with delta, lap times. Added the AST whitelist, the subprocess runner with limits, and the token-protected registry.
- **Checks**: ruff; pytest; live test of trackmap, telemetry, compare, lap-times
- **Decisions/notes**: Non-finite values become null in JSON. Distance grids start at 0. Time grids use the shared stream window. Registration is idempotent by SHA-256. The runner refuses NaN in the output.

### [2026-10-12] app — M3 main screen

- **Files**: app/app.py, app/config.py, app/templates/*.html, app/static/css/style.css, app/static/js/{main,charts,timeline,screens,screen}.js
- **Change**: Added the dashboard: event and session selection, driver list, timeline, track map, mini telemetry, compare, builder box, and the screen pages. The app proxies requests to the server and the builder.
- **Checks**: ruff; page and proxy tests against the live server
- **Decisions/notes**: The browser talks only to the app origin through /server/... and /builder/.... The compare result shows the channel chart and the delta chart. The chat box is a placeholder until M5.

### [2026-10-12] builder — M4 agent, mock mode, and gates

- **Files**: builder/app.py, builder/agent.py, builder/llm.py, builder/prompts.py, builder/server_client.py, tests/test_builder.py
- **Change**: Added the builder service. It writes code with an OpenAI-compatible LLM or the mock. It runs the gates in order: AST validation, ruff, server registration, smoke test. It saves the screen spec. It refuses out-of-scope requests.
- **Checks**: ruff; pytest; live test: two screens built, one refusal
- **Decisions/notes**: The placeholders auto1, auto2, and "fastest" resolve to real values before the smoke test. A registration failure stops the loop, because an LLM retry cannot fix a token problem.

### [2026-10-12] builder — registered screen `speed_compare_2c170b5f`
- **Files**: server/registry/generated/speed_compare_2c170b5f.py, server/registry/generated/speed_compare_2c170b5f.json, builder/screens/speed_compare_2c170b5f.json
- **Change**: Built a screen for the instruction: "Compare the speed of the two fastest drivers"
- **Checks**: AST validation, ruff check, server re-validation, smoke test passed
- **Decisions/notes**: Screen title: Speed compare

### [2026-10-12] builder — registered screen `stint_pace_896da8fd`
- **Files**: server/registry/generated/stint_pace_896da8fd.py, server/registry/generated/stint_pace_896da8fd.json, builder/screens/stint_pace_896da8fd.json
- **Change**: Built a screen for the instruction: "Show the tyre stint pace of the two fastest drivers"
- **Checks**: AST validation, ruff check, server re-validation, smoke test passed
- **Decisions/notes**: Screen title: Stint pace

### [2026-10-12] server and app — compare fix and track map upgrade

- **Files**: server/analysis.py, server/catalog.py, builder/llm.py, builder/prompts.py, app/templates/index.html, app/static/css/style.css, app/static/js/main.js, app/static/js/charts.js
- **Change**: Fixed the compare error. fastf1 pick_fastest returns None for a lap that is not a personal best. One specific lap now uses only_by_time=True. Rebuilt the track map: 5 m grid, smoothed line, grey base track, green-to-red speed heat, driver dot with play and pause. Moved the comparison result to its own tab above the track map. Moved the timeline to a full-width bar with flexible lap chips.
- **Checks**: ruff; pytest; live test: HAM L24 telemetry, compare VER L11 against HAM L24, new track map format, one new build
- **Decisions/notes**: Speed heat: green is slow, red is fast. The track line is 8 px wide and the dot is 6 px. The play button moves the dot in real time over the lap duration. The race session can also have laps that are not personal bests; the fix covers the timeline clicks too.

### [2026-10-12] builder — honest refusals, instruction-aware refs, separate screen ids

- **Files**: builder/llm.py, builder/agent.py, builder/app.py, builder/prompts.py, app/static/js/screens.js, tests/test_builder.py
- **Change**: The mock no longer substitutes a canned analysis for an unrelated instruction. It refuses unavailable data (for example steering angle) and unmatched instructions. The builder reads driver names and lap numbers from the instruction. Screen ids come from the request, so screens do not overwrite each other. Mock screens carry a mock mark in the screens list.
- **Checks**: ruff; pytest (52 tests); live test: steering refusal, Hamilton L8 against L13, Verstappen against Russell on SQ
- **Decisions/notes**: Steering angle is not in the public FastF1 data. The builder must refuse it and name the available channels. Keyword matching uses whole words, because "gap" must not match "Singapore". Instruction overrides apply before placeholder resolution, so the fastest lap belongs to the final driver. The function id comes from the code; the screen id comes from the request.

### [2026-10-12] project — housekeeping and first full commit

- **Files**: builder/screens/, server/registry/generated/, removed the stray -fsSL file
- **Change**: Removed duplicate test screens and functions. Kept four screens: Hamilton speed, Hamilton throttle, Verstappen against Russell, and stint pace. Two functions serve all four screens.
- **Checks**: ruff; pytest (52 tests)
- **Decisions/notes**: Generated code and screen specs stay gitignored runtime artifacts. The first full commit holds the complete system. Use ./run.sh to start all services.

### [2026-10-12] server and app — M5b F1TV access and gated live capture

- **Files**: server/live.py, server/routes/live.py, server/session_manager.py, server/catalog.py, server/config.py, server/app.py, app/templates/index.html, app/static/css/style.css, app/static/js/live.js, app/static/js/main.js, tests/test_live.py, .gitignore, README.md, plan.md
- **Change**: Added the F1TV access flow and gated live timing. The app asks for access before any capture. The server runs the FastF1 browser login with a local callback server, verifies the token, and captures the live stream with SignalRClient. Stop or a 5-minute silence timeout ends the capture and loads it as a normal session.
- **Checks**: ruff; pytest (59 tests); live test of all gate endpoints without credentials
- **Decisions/notes**: The token file is the FastF1 auth file. The callback server copies fastf1 internals (f1auth); the fastf1 version is pinned in uv.lock. ManagedSignalRClient adds a clean stop, because the fastf1 client has none. The live window check runs 15 minutes before a session until 3 hours after it. Capture must be validated during a live weekend with an F1TV subscription; it is not testable now.

### [2026-10-12] builder — registered screen `speed_compare_31158dde`
- **Files**: server/registry/generated/speed_compare_31158dde.py, server/registry/generated/speed_compare_31158dde.json, builder/screens/speed_compare_31158dde.json
- **Change**: Built a screen for the instruction: "Compare the speed of VER and HAM at Singapore"
- **Checks**: AST validation, ruff check, server re-validation, smoke test passed
- **Decisions/notes**: Screen title: Speed compare

### [2026-10-12] builder — registered screen `speed_compare_31158dde`
- **Files**: server/registry/generated/speed_compare_31158dde.py, server/registry/generated/speed_compare_31158dde.json, builder/screens/speed_compare_31158dde.json
- **Change**: Built a screen for the instruction: "Compare Hamilton steering angles over the laps 8 and 13 (sprint qualifying) over the track distance (Positive steering left and negative steering to right)"
- **Checks**: AST validation, ruff check, server re-validation, smoke test passed
- **Decisions/notes**: Screen title: Speed compare

### [2026-10-12] builder — registered screen `speed_compare_31158dde`
- **Files**: server/registry/generated/speed_compare_31158dde.py, server/registry/generated/speed_compare_31158dde.json, builder/screens/speed_compare_31158dde.json
- **Change**: Built a screen for the instruction: "Compare Hamilton laps 8 and 13 speed over the track distance"
- **Checks**: AST validation, ruff check, server re-validation, smoke test passed
- **Decisions/notes**: Screen title: Speed compare

### [2026-10-12] builder — registered screen `speed_compare_04cfd060` (function `speed_compare_31158dde`)
- **Files**: server/registry/generated/speed_compare_31158dde.py, server/registry/generated/speed_compare_31158dde.json, builder/screens/speed_compare_04cfd060.json
- **Change**: Built a screen for the instruction: "Compare Hamilton laps 8 and 13 speed over the track distance"
- **Checks**: AST validation, ruff check, server re-validation, smoke test passed
- **Decisions/notes**: Screen title: Speed compare

### [2026-10-12] builder — registered screen `speed_compare_04cfd060` (function `speed_compare_7495591f`)
- **Files**: server/registry/generated/speed_compare_7495591f.py, server/registry/generated/speed_compare_7495591f.json, builder/screens/speed_compare_04cfd060.json
- **Change**: Built a screen for the instruction: "Compare Hamilton laps 8 and 13 speed over the track distance"
- **Checks**: AST validation, ruff check, server re-validation, smoke test passed
- **Decisions/notes**: Screen title: Speed compare

### [2026-10-12] builder — registered screen `speed_compare_17c9bf6e` (function `speed_compare_7495591f`)
- **Files**: server/registry/generated/speed_compare_7495591f.py, server/registry/generated/speed_compare_7495591f.json, builder/screens/speed_compare_17c9bf6e.json
- **Change**: Built a screen for the instruction: "Compare Verstappen and Russell speed over the track distance"
- **Checks**: AST validation, ruff check, server re-validation, smoke test passed
- **Decisions/notes**: Screen title: Speed compare

### [2026-10-12] builder — registered screen `speed_compare_50a5720d` (function `speed_compare_7495591f`)
- **Files**: server/registry/generated/speed_compare_7495591f.py, server/registry/generated/speed_compare_7495591f.json, builder/screens/speed_compare_50a5720d.json
- **Change**: Built a screen for the instruction: "Compare Hamilton laps 8 and 13 throttle over the track distance"
- **Checks**: AST validation, ruff check, server re-validation, smoke test passed
- **Decisions/notes**: Screen title: Speed compare

### [2026-10-12] builder — registered screen `speed_compare_5f8812a5` (function `speed_compare_7495591f`)
- **Files**: server/registry/generated/speed_compare_7495591f.py, server/registry/generated/speed_compare_7495591f.json, builder/screens/speed_compare_5f8812a5.json
- **Change**: Built a screen for the instruction: "Compare drivers full throttle with drops in acceleration, make a graph of the eletric engine gaps over a lap"
- **Checks**: AST validation, ruff check, server re-validation, smoke test passed
- **Decisions/notes**: Screen title: Speed compare

### [2026-10-12] server, app, and builder — steering wheel input estimate from the X and Y positions
- **Files**: server/normalize.py, server/analysis.py, server/routes/analysis.py, app/templates/index.html, builder/llm.py, builder/prompts.py, tests/test_normalize.py, tests/test_analysis.py, tests/test_builder.py
- **Change**: Added the steering input method. FastF1 has no steering angle channel. The method estimates the steering wheel input from the X and Y positions. The heading change between two positions gives the curvature of the driven line. A tight curve gives a large input. The values run from -100 (steering to the right) to +100 (steering to the left). Added the route /api/analysis/steering-input. The telemetry and compare routes accept the channel SteeringInput. The app compare form has a "Steering input" channel. The builder mock builds steering screens in place of the old refusal. The builder prompt documents the estimate.
- **Checks**: ruff check; ruff format --check; pytest (71 tests); live test on the cached Singapore 2026 Qualifying session: the new route, the compare channel, and the mock function through the registry sandbox
- **Decisions/notes**: X and Y use the unit 1/10 m. The method smooths the positions with a moving average of 5 samples and smooths the curvature with a moving average of 5 samples. The sign follows the track map: positive is a counterclockwise turn (left), negative is a clockwise turn (right). The largest curvature in the lap sets the scale. Each lap uses its own scale, because the data has no absolute steering scale. The value is an estimate, not sensor data.
