"""Seed analysis routes. Each route returns one envelope."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from server import analysis
from server.session_manager import MANAGER

bp = Blueprint("analysis", __name__, url_prefix="/api/analysis")


def _session(year, round_number, code):
    return MANAGER.require(MANAGER.key(int(year), int(round_number), str(code)))


@bp.get("/trackmap")
def trackmap():
    session = _session(request.args["year"], request.args["round"], request.args["code"])
    driver = request.args.get("driver") or None
    channel = request.args.get("channel", "Speed")
    return jsonify(analysis.trackmap(session, driver, channel))


@bp.get("/telemetry")
def telemetry():
    session = _session(request.args["year"], request.args["round"], request.args["code"])
    return jsonify(
        analysis.telemetry(
            session,
            request.args["driver"],
            request.args.get("lap", type=int),
            request.args.get("channel", "Speed"),
            request.args.get("axis", "distance"),
        )
    )


@bp.post("/compare")
def compare():
    body = request.get_json(force=True, silent=True) or {}
    ref = body.get("session") or {}
    session = _session(ref.get("year"), ref.get("round"), ref.get("code"))
    mode = str(body.get("normalize", "length"))
    axis = "time" if mode == "timespan" else "distance"
    return jsonify(
        analysis.compare(
            session,
            refs=body.get("refs") or [],
            channel=str(body.get("channel", "Speed")),
            axis=axis,
            delta=bool(body.get("delta", True)),
        )
    )


@bp.get("/lap-times")
def lap_times():
    session = _session(request.args["year"], request.args["round"], request.args["code"])
    drivers = request.args.get("drivers")
    driver_list = [driver for driver in drivers.split(",") if driver] if drivers else None
    return jsonify(analysis.lap_times(session, driver_list))
