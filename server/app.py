"""Data server entry point. Start it with `uv run python -m server.app`."""

from __future__ import annotations

import json
import logging

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from server import registry
from server.config import SERVER_PORT
from server.routes import analysis, catalog, live
from server.routes import registry as registry_routes
from server.session_manager import SessionNotReadyError


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(catalog.bp)
    app.register_blueprint(analysis.bp)
    app.register_blueprint(registry_routes.bp)
    app.register_blueprint(live.bp)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.errorhandler(SessionNotReadyError)
    def handle_not_ready(error: SessionNotReadyError):
        return jsonify({"error": str(error), "state": error.state}), 409

    @app.errorhandler(ValueError)
    def handle_value_error(error: ValueError):
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(registry.RegistrationError)
    def handle_registration_error(error: registry.RegistrationError):
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(registry.RunError)
    def handle_run_error(error: registry.RunError):
        return jsonify({"error": str(error)}), 500

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException):
        response = error.get_response()
        response.data = json.dumps({"error": error.description})
        response.content_type = "application/json"
        return response

    @app.errorhandler(Exception)
    def handle_error(error: Exception):
        app.logger.exception("unexpected server error")
        return jsonify({"error": f"internal error: {error}"}), 500

    return app


app = create_app()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="127.0.0.1", port=SERVER_PORT)
