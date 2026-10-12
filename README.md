# Telemetry Tracker

An interface to review and analyze Formula 1 telemetry from the [FastF1](https://docs.fastf1.dev) Python API.

The system has three services:

| Service | Port | Job |
|---|---|---|
| `server/` | 5001 | Retrieves and normalizes FastF1 data. Holds the registry of analysis functions. |
| `app/` | 5000 | Flask user interface (event/session selection, track map, telemetry, compare, builder box). |
| `builder/` | 5002 | Agent that turns natural-language instructions into registered FastF1 analysis screens. |

The project premises and the change log live in [agent.md](agent.md). The implementation plan lives in [plan.md](plan.md).

## Quick start

```bash
# 1. Install uv (once), then:
uv sync

# 2. Copy the environment file and change the values:
cp .env.example .env

# 3. Start all three services:
./run.sh
# or start them in separate terminals:
uv run python -m server.app     # data server   :5001
uv run python -m app.app        # user interface :5000
uv run python -m builder.app    # builder agent  :5002

# 4. Open http://127.0.0.1:5000
```

The first load of a session downloads data from the F1 timing servers. This can take minutes. Later loads use the cache in `data/cache/`.

## Checks

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

## Notes

- The builder runs in mock mode by default (`LLM_MOCK=1` in `.env`). It returns known-good analyses, so no API key is necessary. Set `LLM_MOCK=0` and fill the `LLM_*` values to use a real OpenAI-compatible endpoint.
- The app asks for F1TV access before it tries live timing. Live timing is planned for M5.
- All texts in this project follow ASD-STE100 Simplified Technical English. See `agent.md`, section 6.
