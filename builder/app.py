"""Builder service entry point. Start it with `uv run python -m builder.app`."""

from __future__ import annotations

import json
import re

from flask import Flask, jsonify, request

from builder import config
from builder.agent import build_screen

SCREEN_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,60}$")


def list_screens() -> list[dict]:
    """Return a summary of every saved screen, newest first."""
    screens = []
    for path in sorted(config.SCREENS_DIR.glob("*.json")):
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        screens.append(
            {key: spec.get(key) for key in ("id", "title", "instruction", "created", "mock")}
        )
    screens.sort(key=lambda item: item.get("created") or "", reverse=True)
    return screens


def get_screen(screen_id: str) -> dict | None:
    """Return one screen spec. None if unknown."""
    if not SCREEN_ID_RE.match(screen_id):
        return None
    path = config.SCREENS_DIR / f"{screen_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "mock": config.LLM_MOCK})

    @app.post("/build")
    def build():
        body = request.get_json(force=True, silent=True) or {}
        instruction = str(body.get("instruction", "")).strip()
        if not instruction:
            return jsonify({"error": "the instruction field is required"}), 400
        return jsonify(build_screen(instruction, body.get("context") or {}))

    @app.get("/screens")
    def screens():
        return jsonify({"screens": list_screens()})

    @app.get("/screens/<screen_id>")
    def screen(screen_id: str):
        spec = get_screen(screen_id)
        if spec is None:
            return jsonify({"error": f"unknown screen: {screen_id}"}), 404
        return jsonify({"screen": spec})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=config.BUILDER_PORT, threaded=True)
