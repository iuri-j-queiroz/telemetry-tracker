"""Live timing routes. F1TV access flow and gated capture.

The app asks for F1TV access before any live attempt. See plan.md, section 10.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from server import live

bp = Blueprint("live", __name__, url_prefix="/api/live")


@bp.get("/status")
def status():
    return jsonify(live.live_status())


@bp.post("/auth/start")
def auth_start():
    return jsonify(live.start_auth())


@bp.get("/auth/state")
def auth_state():
    return jsonify(live.auth_info())


@bp.post("/auth/cancel")
def auth_cancel():
    return jsonify(live.cancel_auth())


@bp.post("/auth/clear")
def auth_clear():
    return jsonify(live.clear_credentials())


@bp.post("/capture/start")
def capture_start():
    body = request.get_json(force=True, silent=True) or {}
    session = body.get("session") or {}
    try:
        clean = {
            "year": int(session["year"]),
            "round": int(session["round"]),
            "code": str(session["code"]),
        }
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "give a session with year, round, and code"}), 400
    return jsonify(live.CAPTURE.start(clean))


@bp.get("/capture/state")
def capture_state():
    return jsonify(live.CAPTURE.info())


@bp.post("/capture/stop")
def capture_stop():
    return jsonify(live.CAPTURE.stop())
