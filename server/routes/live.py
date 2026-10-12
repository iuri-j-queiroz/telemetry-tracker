"""Live timing routes. Planned for M5.

The app asks for F1TV access before any live attempt. See agent.md, section 2,
and plan.md, section 10.
"""

from __future__ import annotations

from flask import Blueprint, jsonify

bp = Blueprint("live", __name__, url_prefix="/api/live")

LIVE_REASON = (
    "Live timing is not available in this milestone. "
    "The app replays the latest completed session instead."
)


@bp.get("/status")
def status():
    return jsonify({"available": False, "has_credentials": False, "reason": LIVE_REASON})


@bp.post("/auth")
def auth():
    return jsonify({"error": LIVE_REASON}), 501
