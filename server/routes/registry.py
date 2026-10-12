"""Registry routes. The server is the authority for registration."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from server import config, registry

bp = Blueprint("registry", __name__, url_prefix="/api/registry")


@bp.get("/")
def list_functions():
    return jsonify({"functions": registry.list_functions()})


@bp.get("/<function_id>")
def get_function(function_id: str):
    metadata = registry.get_function(function_id)
    if metadata is None:
        return jsonify({"error": f"unknown function: {function_id}"}), 404
    return jsonify({"function": metadata})


@bp.post("/register")
def register():
    token = request.headers.get("X-Builder-Token", "")
    if not config.BUILDER_TOKEN or token != config.BUILDER_TOKEN:
        return jsonify({"error": "registration is refused: bad or missing token"}), 403
    body = request.get_json(force=True, silent=True) or {}
    source = body.get("source")
    if not isinstance(source, str) or not source.strip():
        return jsonify({"error": "the source field is required"}), 400
    metadata = registry.register(
        str(body.get("instruction", "")),
        source,
        body.get("meta") or {},
    )
    return jsonify({"function": metadata}), 201


@bp.post("/<function_id>/run")
def run_function(function_id: str):
    body = request.get_json(force=True, silent=True) or {}
    envelope = registry.run(
        function_id,
        params=body.get("params") or {},
        session=body.get("session"),
    )
    return jsonify(envelope)
