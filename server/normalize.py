"""Normalize telemetry data. Two patterns: time span and track length.

Data goes onto one shared grid in both patterns. This code also serves
registered functions. Keep the API stable.

- Timespan: one time grid. Use session time for streams at the same moment.
  Use lap-relative time for lap comparisons.
- Length: one distance grid from 0 to the track length.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def time_seconds(values) -> np.ndarray:
    """Convert a time column to a float array of seconds.

    Accepts pandas Series or numpy arrays with timedelta64, datetime64,
    or numeric values.
    """
    if isinstance(values, pd.Series):
        if pd.api.types.is_timedelta64_dtype(values):
            return values.dt.total_seconds().to_numpy(dtype=float)
        if pd.api.types.is_datetime64_any_dtype(values):
            return (values - values.iloc[0]).dt.total_seconds().to_numpy(dtype=float)
        return values.to_numpy(dtype=float)
    array = np.asarray(values)
    if np.issubdtype(array.dtype, np.timedelta64):
        return array / np.timedelta64(1, "s")
    if np.issubdtype(array.dtype, np.datetime64):
        return (array - array[0]) / np.timedelta64(1, "s")
    return array.astype(float)


def envelope(
    kind: str,
    *,
    x: dict | None = None,
    series: list | None = None,
    meta: dict | None = None,
    **extra,
) -> dict:
    """Build one envelope. See agent.md, section 3."""
    result: dict = {"kind": kind}
    if x is not None:
        result["x"] = x
    if series is not None:
        result["series"] = series
    if meta is not None:
        result["meta"] = meta
    result.update(extra)
    return result


def values_list(values: np.ndarray) -> list:
    """Convert an array to a JSON-safe list. Non-finite values become None."""
    array = np.asarray(values, dtype=float)
    return [None if not np.isfinite(v) else float(v) for v in array]


def grid(lo: float, hi: float, step: float) -> np.ndarray:
    """Return a grid from lo to hi with the given step."""
    if not np.isfinite([lo, hi]).all() or hi < lo or step <= 0:
        return np.array([])
    count = int(np.floor((hi - lo) / step)) + 1
    return lo + np.arange(count) * step


def resample(x, y, new_x) -> np.ndarray:
    """Interpolate y(x) onto new_x. Returns NaN outside the source range."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    new_x = np.asarray(new_x, dtype=float)
    if x.size == 0 or new_x.size == 0:
        return np.full(new_x.shape, np.nan)
    order = np.argsort(x, kind="stable")
    x, y = x[order], y[order]
    keep = np.isfinite(x) & np.isfinite(y)
    x, y = x[keep], y[keep]
    if x.size == 0:
        return np.full(new_x.shape, np.nan)
    unique_x, first = np.unique(x, return_index=True)
    values = np.interp(new_x, unique_x, y[first])
    outside = (new_x < unique_x[0]) | (new_x > unique_x[-1])
    values[outside] = np.nan
    return values


def _window(streams: dict, start: float | None, end: float | None) -> tuple[float, float]:
    firsts = [float(np.nanmin(x)) for x, _ in streams.values() if np.asarray(x).size]
    lasts = [float(np.nanmax(x)) for x, _ in streams.values() if np.asarray(x).size]
    if not firsts:
        return float("nan"), float("nan")
    lo = max(firsts)
    hi = min(lasts)
    if start is not None:
        lo = max(lo, start)
    if end is not None:
        hi = min(hi, end)
    return lo, hi


def normalize_streams(
    streams: dict,
    channel: str,
    axis: str,
    *,
    step: float | None = None,
    track_length: float | None = None,
    start: float | None = None,
    end: float | None = None,
) -> dict:
    """Normalize streams onto one grid and return one envelope.

    streams: dict[label, (x_values, y_values)]
    axis: "distance" or "time"
    """
    if axis not in ("distance", "time"):
        raise ValueError(f"unknown axis: {axis}")
    if step is None:
        step = 5.0 if axis == "distance" else 0.1
    if axis == "distance":
        # The track governs the grid: 0 to the track length.
        lasts = [float(np.nanmax(x)) for x, _ in streams.values() if np.asarray(x).size]
        lo = 0.0 if start is None else start
        hi = min(lasts) if lasts else float("nan")
        if track_length is not None:
            hi = min(float(track_length), max(lasts)) if lasts else float(track_length)
        if end is not None:
            hi = min(hi, end)
    else:
        # Use the shared window: compare only while every stream has data.
        lo, hi = _window(streams, start, end)
    points = grid(lo, hi, step)
    series = []
    for label, (x, y) in streams.items():
        series.append({"label": label, "values": values_list(resample(x, y, points))})
    x_info = {
        "name": axis,
        "unit": "m" if axis == "distance" else "s",
        "values": values_list(points),
    }
    return envelope("telemetry", x=x_info, series=series, meta={"channel": channel, "axis": axis})


def normalize_length(
    streams: dict,
    channel: str,
    *,
    track_length: float | None = None,
    step_m: float = 5.0,
) -> dict:
    """Normalize streams on the track length. The standard for lap comparisons."""
    return normalize_streams(streams, channel, "distance", step=step_m, track_length=track_length)


def normalize_timespan(
    streams: dict,
    channel: str,
    *,
    step_s: float = 0.1,
    start: float | None = None,
    end: float | None = None,
) -> dict:
    """Normalize streams on one time grid. Pass lap-relative times for lap compares."""
    return normalize_streams(streams, channel, "time", step=step_s, start=start, end=end)


def compute_delta(values_a: list, values_b: list) -> list:
    """Return values_b minus values_a. None stays None."""
    out = []
    for a, b in zip(values_a, values_b, strict=False):
        out.append(None if a is None or b is None else b - a)
    return out
