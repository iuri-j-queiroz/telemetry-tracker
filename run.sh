#!/usr/bin/env bash
# Start the server, the app, and the builder.
# Stop all services with Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$PATH"

trap 'kill 0' EXIT

uv run python -m server.app &
uv run python -m app.app &
uv run python -m builder.app &

wait
