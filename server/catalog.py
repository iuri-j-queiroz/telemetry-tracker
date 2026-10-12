"""Read the FastF1 calendar and the session details."""

from __future__ import annotations

import datetime as dt
from functools import lru_cache

import fastf1
import fastf1.plotting
import pandas as pd

SESSION_CODES = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
    "Sprint": "S",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SS",
    "Race": "R",
}


@lru_cache(maxsize=16)
def _schedule(year: int) -> pd.DataFrame:
    return fastf1.get_event_schedule(year, include_testing=False)


def _is_completed(moment) -> bool:
    if moment is None or pd.isna(moment):
        return False
    if getattr(moment, "tzinfo", None) is None:
        moment = moment.tz_localize("UTC")
    return bool(moment <= pd.Timestamp.now(tz="UTC"))


def live_window(now=None) -> dict | None:
    """Return the session that is in progress now. None otherwise.

    A session is live from 15 minutes before the start until 3 hours after it.
    """
    moment = now or dt.datetime.now(dt.UTC)
    try:
        schedule = _schedule(moment.year)
    except Exception:  # noqa: BLE001 - the live check must never raise
        return None
    for _, row in schedule.iterrows():
        if int(row["RoundNumber"]) == 0:
            continue
        for index in range(1, 6):
            name = row.get(f"Session{index}")
            start = row.get(f"Session{index}DateUtc")
            if not isinstance(name, str) or pd.isna(start):
                continue
            if getattr(start, "tzinfo", None) is None:
                start = start.tz_localize("UTC")
            if start - dt.timedelta(minutes=15) <= moment <= start + dt.timedelta(hours=3):
                return {
                    "year": moment.year,
                    "round": int(row["RoundNumber"]),
                    "name": str(row["EventName"]),
                    "session": name,
                    "code": SESSION_CODES.get(name, name[:3].upper()),
                    "start": start.isoformat(),
                }
    return None


def list_events(years: int = 3) -> list[dict]:
    """Return the calendar of completed seasons, newest event first."""
    today = dt.datetime.now(dt.UTC)
    events = []
    for year in range(today.year, today.year - max(1, years), -1):
        try:
            schedule = _schedule(year)
        except Exception:  # noqa: BLE001, S112 - a missing season must not kill the list
            continue
        for _, row in schedule.iterrows():
            moment = row["EventDate"]
            if moment is None or pd.isna(moment):
                continue
            events.append(
                {
                    "year": year,
                    "round": int(row["RoundNumber"]),
                    "name": str(row["EventName"]),
                    "official_name": str(row["OfficialEventName"]),
                    "country": str(row["Country"]),
                    "location": str(row["Location"]),
                    "date": moment.date().isoformat(),
                    "completed": _is_completed(moment),
                }
            )
    events.sort(key=lambda event: event["date"], reverse=True)
    return events


def list_sessions(year: int, round_number: int) -> list[dict]:
    """Return the sessions of one event, in running order."""
    schedule = _schedule(year)
    rows = schedule[schedule["RoundNumber"] == round_number]
    if rows.empty:
        raise ValueError(f"unknown event: {year} round {round_number}")
    row = rows.iloc[0]
    sessions = []
    for index in range(1, 6):
        name = row.get(f"Session{index}")
        moment = row.get(f"Session{index}Date")
        moment_utc = row.get(f"Session{index}DateUtc")
        if not isinstance(name, str) or pd.isna(moment):
            continue
        completed_check = moment_utc if isinstance(moment_utc, pd.Timestamp) else moment
        sessions.append(
            {
                "code": SESSION_CODES.get(name, name[:3].upper()),
                "name": name,
                "date": moment.isoformat(),
                "completed": _is_completed(completed_check),
            }
        )
    return sessions


def driver_color(session, code: str) -> str:
    """Return the team color of one driver. Grey on failure."""
    try:
        return fastf1.plotting.get_driver_color(code, session=session)
    except Exception:  # noqa: BLE001 - the color is cosmetic
        return "#888888"


def list_drivers(session) -> list[dict]:
    """Return the drivers of a loaded session."""
    results = getattr(session, "results", None)
    if results is not None and len(results):
        drivers = []
        for _, row in results.iterrows():
            code = str(row.get("Abbreviation", ""))
            drivers.append(
                {
                    "number": str(row.get("DriverNumber", "")),
                    "code": code,
                    "name": str(row.get("FullName", code)),
                    "team": str(row.get("TeamName", "")),
                    "color": driver_color(session, code),
                }
            )
        return drivers
    seen: dict[str, str] = {}
    for number, code in zip(session.laps["DriverNumber"], session.laps["Driver"], strict=False):
        seen[str(number)] = str(code)
    return [
        {
            "number": number,
            "code": code,
            "name": code,
            "team": "",
            "color": driver_color(session, code),
        }
        for number, code in sorted(seen.items(), key=lambda item: item[1])
    ]


def list_laps(session, driver: str) -> list[dict]:
    """Return the laps of one driver."""
    laps = session.laps.pick_drivers(driver)
    out = []
    for _, lap in laps.iterrows():
        lap_time = lap.get("LapTime")
        compound = lap.get("Compound")
        stint = lap.get("Stint")
        out.append(
            {
                "number": int(lap["LapNumber"]),
                "time_s": float(lap_time.total_seconds()) if pd.notna(lap_time) else None,
                "compound": str(compound) if pd.notna(compound) else None,
                "stint": int(stint) if pd.notna(stint) else None,
                "accurate": bool(lap.get("IsAccurate", False)),
            }
        )
    return out


def fastest_lap_number(session, driver: str) -> int | None:
    """Return the lap number of the fastest lap of one driver."""
    try:
        fastest = session.laps.pick_drivers(driver).pick_fastest()
        if fastest is None:
            fastest = session.laps.pick_drivers(driver).pick_fastest(only_by_time=True)
    except Exception:  # noqa: BLE001 - a driver without a timed lap is possible
        return None
    if fastest is None:
        return None
    return int(fastest["LapNumber"])
