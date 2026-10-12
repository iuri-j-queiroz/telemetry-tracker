"""Tests for the normalization module."""

import numpy as np

from server import normalize


def test_time_seconds_with_timedelta():
    values = np.array([0, 1_500_000_000, 3_000_000_000], dtype="timedelta64[ns]")
    seconds = normalize.time_seconds(values)
    assert seconds.tolist() == [0.0, 1.5, 3.0]


def test_time_seconds_with_numbers():
    assert normalize.time_seconds([1, 2, 3]).tolist() == [1.0, 2.0, 3.0]


def test_grid_has_the_right_points():
    points = normalize.grid(0.0, 10.0, 5.0)
    assert points.tolist() == [0.0, 5.0, 10.0]


def test_grid_clips_at_the_last_full_step():
    points = normalize.grid(0.0, 11.0, 5.0)
    assert points.tolist() == [0.0, 5.0, 10.0]


def test_grid_is_empty_for_a_bad_range():
    assert normalize.grid(5.0, 1.0, 1.0).size == 0


def test_resample_interpolates():
    x = np.array([0.0, 10.0])
    y = np.array([0.0, 100.0])
    values = normalize.resample(x, y, np.array([0.0, 5.0, 10.0]))
    assert values.tolist() == [0.0, 50.0, 100.0]


def test_resample_returns_nan_outside_the_source_range():
    x = np.array([0.0, 10.0])
    y = np.array([0.0, 100.0])
    values = normalize.resample(x, y, np.array([-1.0, 5.0, 11.0]))
    assert np.isnan(values[0]) and values[1] == 50.0 and np.isnan(values[2])


def test_normalize_length_uses_the_shared_window():
    streams = {
        "A": (np.array([0.0, 100.0]), np.array([0.0, 200.0])),
        "B": (np.array([50.0, 150.0]), np.array([500.0, 700.0])),
    }
    envelope = normalize.normalize_length(streams, "Speed", track_length=150.0, step_m=50.0)
    assert envelope["kind"] == "telemetry"
    assert envelope["x"]["name"] == "distance"
    assert envelope["x"]["values"] == [0.0, 50.0, 100.0, 150.0]
    series = {item["label"]: item["values"] for item in envelope["series"]}
    assert series["A"][:3] == [0.0, 100.0, 200.0]
    assert series["A"][3] is None
    assert series["B"][0] is None
    assert series["B"][1:] == [500.0, 600.0, 700.0]


def test_normalize_timespan_clips_to_the_start_and_end():
    streams = {
        "A": (np.array([0.0, 10.0]), np.array([0.0, 10.0])),
        "B": (np.array([2.0, 8.0]), np.array([20.0, 80.0])),
    }
    envelope = normalize.normalize_timespan(streams, "Speed", step_s=1.0)
    assert envelope["x"]["unit"] == "s"
    assert envelope["x"]["values"][0] == 2.0
    assert envelope["x"]["values"][-1] == 8.0


def test_compute_delta_keeps_none():
    assert normalize.compute_delta([1.0, None, 3.0], [3.0, 4.0, None]) == [2.0, None, None]
