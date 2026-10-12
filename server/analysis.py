"""Seed analyses. Each function returns one envelope. See agent.md, section 3."""

from __future__ import annotations

import numpy as np
import pandas as pd

from server import normalize
from server.catalog import driver_color

CHANNELS = ("Speed", "Throttle", "Brake", "nGear", "RPM", "DRS")

UNITS = {
    "Speed": "km/h",
    "Throttle": "%",
    "Brake": "%",
    "nGear": "gear",
    "RPM": "rpm",
    "DRS": "code",
    "SteeringInput": "%",
}


def _lap(session, driver: str | None = None, lap_number: int | None = None):
    """Pick one lap. Without a lap number, pick the fastest lap of the selection.

    A lap can have a lap time and still not be a personal best, for example
    after a deleted lap. pick_fastest returns None then. Use the time order
    for one specific lap, and as a fallback for the fastest lap.
    """
    laps = session.laps
    if driver:
        laps = laps.pick_drivers(driver)
    if lap_number is not None:
        laps = laps.pick_laps(lap_number)
    laps = laps[pd.notna(laps["LapTime"])]
    if laps.empty:
        raise ValueError("no lap with a lap time for this selection")
    if lap_number is not None:
        return laps.pick_fastest(only_by_time=True)
    lap = laps.pick_fastest()
    if lap is None:
        lap = laps.pick_fastest(only_by_time=True)
    if lap is None:
        raise ValueError("no lap data for this selection")
    return lap


def lap_telemetry(lap) -> pd.DataFrame:
    telemetry = lap.get_telemetry()
    if "Distance" not in telemetry.columns:
        telemetry = telemetry.add_distance()
    return telemetry


def label_of(lap) -> str:
    return f"{lap['Driver']} L{int(lap['LapNumber'])}"


def _smooth(values: np.ndarray, window: int = 5) -> np.ndarray:
    """Moving average with edge padding. Makes the track line streamlined."""
    return normalize.moving_average(values, window)


def _x_values(telemetry: pd.DataFrame, axis: str) -> np.ndarray:
    if axis == "distance":
        return telemetry["Distance"].to_numpy(dtype=float)
    if axis == "time":
        return normalize.time_seconds(telemetry["Time"])
    raise ValueError(f"unknown axis: {axis}")


def _channel_values(telemetry: pd.DataFrame, channel: str) -> np.ndarray:
    if channel == "SteeringInput":
        if not {"X", "Y"}.issubset(telemetry.columns):
            raise ValueError("channel SteeringInput needs the X and Y positions")
        return normalize.steering_input(telemetry["X"], telemetry["Y"])
    if channel not in telemetry.columns:
        raise ValueError(f"channel {channel} is not in the telemetry")
    return telemetry[channel].to_numpy(dtype=float)


def trackmap(
    session, driver: str | None = None, channel: str = "Speed", step_m: float = 5.0
) -> dict:
    """Streamlined track map of the fastest lap.

    Interpolate the full position data onto a fixed distance grid and smooth
    the line. The values give the speed for the heatmap.
    """
    lap = _lap(session, driver)
    frame = lap_telemetry(lap)
    distance = frame["Distance"].to_numpy(dtype=float)
    x = frame["X"].to_numpy(dtype=float)
    y = frame["Y"].to_numpy(dtype=float)
    values = _channel_values(frame, channel) if channel in frame.columns else np.array([])
    finite = np.isfinite(distance)
    if not finite.any():
        raise ValueError("the lap has no position data")
    points = normalize.grid(float(distance[finite][0]), float(distance[finite][-1]), step_m)
    x_grid = _smooth(normalize.resample(distance, x, points))
    y_grid = _smooth(normalize.resample(distance, y, points))
    values_grid = normalize.resample(distance, values, points) if values.size else np.array([])
    finite_values = values_grid[np.isfinite(values_grid)] if values_grid.size else np.array([])
    lap_time = lap["LapTime"]
    return normalize.envelope(
        "trackmap",
        series=[
            {
                "label": label_of(lap),
                "x": normalize.values_list(x_grid),
                "y": normalize.values_list(y_grid),
                "values": normalize.values_list(values_grid),
                "color": driver_color(session, str(lap["Driver"])),
            }
        ],
        meta={
            "track_length_m": float(distance[finite][-1]),
            "lap_time_s": float(lap_time.total_seconds()) if pd.notna(lap_time) else None,
            "step_m": step_m,
            "channel": channel,
            "unit": UNITS.get(channel, ""),
            "driver": str(lap["Driver"]),
            "lap": int(lap["LapNumber"]),
            "vmin": float(np.nanmin(finite_values)) if finite_values.size else None,
            "vmax": float(np.nanmax(finite_values)) if finite_values.size else None,
        },
    )


def telemetry(
    session,
    driver: str,
    lap_number: int | None = None,
    channel: str = "Speed",
    axis: str = "distance",
) -> dict:
    """One channel of one lap on a distance grid or a time grid."""
    lap = _lap(session, driver, lap_number)
    frame = lap_telemetry(lap)
    x = _x_values(frame, axis)
    y = _channel_values(frame, channel)
    track_length = float(np.nanmax(x)) if axis == "distance" else None
    envelope = normalize.normalize_streams(
        {label_of(lap): (x, y)},
        channel,
        axis,
        track_length=track_length,
        start=0.0 if axis == "distance" else None,
    )
    envelope["series"][0]["color"] = driver_color(session, str(lap["Driver"]))
    envelope["meta"].update(
        {
            "driver": str(lap["Driver"]),
            "lap": int(lap["LapNumber"]),
            "unit": UNITS.get(channel, ""),
        }
    )
    return envelope


def steering_input(
    session, driver: str, lap_number: int | None = None, axis: str = "distance"
) -> dict:
    """Steering wheel input of one lap, estimated from the X and Y positions.

    FastF1 has no steering angle channel. The input comes from the curvature
    of the driven line. A tight curve gives a large input. The values run
    from -100 (steering to the right) to +100 (steering to the left).
    """
    envelope = telemetry(session, driver, lap_number, "SteeringInput", axis)
    envelope["meta"].update(
        {
            "channel": "Steering input",
            "estimate": "from the X and Y positions",
            "positive": "left",
            "negative": "right",
        }
    )
    return envelope


def compare(
    session,
    refs: list[dict],
    channel: str = "Speed",
    axis: str = "distance",
    delta: bool = True,
) -> dict:
    """Compare laps of one or two drivers. refs: [{driver, lap}, ...].

    Length normalization is the standard for lap comparisons. The optional delta
    series is the second stream minus the first stream.
    """
    if not refs:
        raise ValueError("give at least one driver and lap reference")
    streams: dict = {}
    colors: dict = {}
    for ref in refs:
        lap = _lap(session, ref.get("driver"), ref.get("lap"))
        frame = lap_telemetry(lap)
        label = label_of(lap)
        streams[label] = (_x_values(frame, axis), _channel_values(frame, channel))
        colors[label] = driver_color(session, str(lap["Driver"]))
    track_length = (
        max(float(np.nanmax(x)) for x, _ in streams.values() if np.asarray(x).size)
        if axis == "distance"
        else None
    )
    envelope = normalize.normalize_streams(
        streams,
        channel,
        axis,
        track_length=track_length,
        start=0.0 if axis == "distance" else None,
    )
    for series in envelope["series"]:
        series["color"] = colors.get(series["label"], "#888888")
    if delta and len(envelope["series"]) == 2:
        first, second = envelope["series"]
        envelope["series"].append(
            {
                "label": f"Delta ({second['label']} - {first['label']})",
                "values": normalize.compute_delta(first["values"], second["values"]),
                "color": "#ffffff",
                "dash": True,
            }
        )
    envelope["meta"].update(
        {
            "unit": UNITS.get(channel, ""),
            "refs": refs,
            "drivers": sorted({ref.get("driver") for ref in refs if ref.get("driver")}),
        }
    )
    return envelope


def lap_times(session, drivers: list[str] | None = None) -> dict:
    """Lap times.

    Qualifying-like sessions: one bar for each driver (fastest lap).
    Race-like sessions: one line for each driver over the lap numbers.
    """
    laps = session.laps
    if drivers:
        laps = laps.pick_drivers(drivers)
    race_like = str(getattr(session, "name", "")) in ("Race", "Sprint")
    if race_like:
        lap_numbers = sorted(int(n) for n in laps["LapNumber"].dropna().unique())
        series = []
        for driver, group in laps.groupby("Driver"):
            times = {
                int(row["LapNumber"]): float(row["LapTime"].total_seconds())
                for _, row in group.iterrows()
                if pd.notna(row["LapTime"])
            }
            series.append(
                {
                    "label": str(driver),
                    "values": [times.get(number) for number in lap_numbers],
                    "color": driver_color(session, str(driver)),
                }
            )
        return normalize.envelope(
            "telemetry",
            x={"name": "lap", "unit": "lap", "values": lap_numbers},
            series=series,
            meta={"mode": "race"},
        )
    rows = []
    for driver, group in laps.groupby("Driver"):
        timed = group[pd.notna(group["LapTime"])]
        if timed.empty:
            continue
        fastest = timed["LapTime"].min()
        rows.append({"driver": str(driver), "time_s": float(fastest.total_seconds())})
    if not rows:
        raise ValueError("no timed laps for this selection")
    rows.sort(key=lambda row: row["time_s"])
    best = rows[0]["time_s"]
    return normalize.envelope(
        "barchart",
        x={"name": "driver", "unit": "", "values": [row["driver"] for row in rows]},
        series=[{"label": "Lap time (s)", "values": [row["time_s"] for row in rows]}],
        meta={
            "mode": "fastest lap",
            "unit": "s",
            "colors": [driver_color(session, row["driver"]) for row in rows],
            "gap_s": [round(row["time_s"] - best, 3) for row in rows],
        },
    )
