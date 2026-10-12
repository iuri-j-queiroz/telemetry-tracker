"""User interface entry point. Start it with `uv run python -m app.app`."""

from __future__ import annotations

import json

import requests
from flask import Flask, Response, render_template, request

from app.config import APP_PORT, BUILDER_URL, PROXY_TIMEOUT_S, SERVER_URL


def _proxy(url: str) -> Response:
    """Forward one request to a backend service."""
    try:
        if request.method == "GET":
            upstream = requests.get(url, params=request.args, timeout=PROXY_TIMEOUT_S)
        else:
            upstream = requests.post(
                url,
                params=request.args,
                json=request.get_json(silent=True),
                timeout=PROXY_TIMEOUT_S,
            )
    except requests.RequestException as error:
        return Response(
            json.dumps({"error": f"service unavailable: {error}"}),
            status=502,
            content_type="application/json",
        )
    return Response(
        upstream.content,
        status=upstream.status_code,
        content_type=upstream.headers.get("Content-Type", "application/json"),
    )


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/screens")
    def screens():
        return render_template("screens.html")

    @app.get("/screens/<screen_id>")
    def screen(screen_id: str):
        return render_template("screen.html", screen_id=screen_id)

    @app.route("/server/<path:rest>", methods=["GET", "POST"])
    def proxy_server(rest: str):
        return _proxy(f"{SERVER_URL}/{rest}")

    @app.route("/builder/<path:rest>", methods=["GET", "POST"])
    def proxy_builder(rest: str):
        return _proxy(f"{BUILDER_URL}/{rest}")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=APP_PORT, threaded=True)
