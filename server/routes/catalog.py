"""Session catalog routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from server import catalog
from server.session_manager import MANAGER

bp = Blueprint("catalog", __name__, url_prefix="/api")


@bp.get("/events")
def events():
    years = request.args.get("years", default=3, type=int)
    return jsonify({"events": catalog.list_events(years=years)})


@bp.get("/events/<int:year>/<int:round_number>/sessions")
def sessions(year: int, round_number: int):
    return jsonify({"sessions": catalog.list_sessions(year, round_number)})


@bp.post("/session/<int:year>/<int:round_number>/<code>/prepare")
def prepare(year: int, round_number: int, code: str):
    return jsonify(MANAGER.prepare(MANAGER.key(year, round_number, code)))


@bp.get("/session/<int:year>/<int:round_number>/<code>/status")
def status(year: int, round_number: int, code: str):
    return jsonify(MANAGER.status(MANAGER.key(year, round_number, code)))


@bp.get("/session/<int:year>/<int:round_number>/<code>/drivers")
def drivers(year: int, round_number: int, code: str):
    session = MANAGER.require(MANAGER.key(year, round_number, code))
    return jsonify({"drivers": catalog.list_drivers(session)})


@bp.get("/session/<int:year>/<int:round_number>/<code>/laps")
def laps(year: int, round_number: int, code: str):
    session = MANAGER.require(MANAGER.key(year, round_number, code))
    driver = request.args.get("driver")
    if not driver:
        return jsonify({"error": "the driver parameter is required"}), 400
    return jsonify(
        {
            "laps": catalog.list_laps(session, driver),
            "fastest": catalog.fastest_lap_number(session, driver),
        }
    )
