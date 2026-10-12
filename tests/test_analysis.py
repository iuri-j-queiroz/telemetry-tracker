"""Tests for the seed analyses. No FastF1 network access."""

import numpy as np
import pandas as pd

from server import analysis


class FakeLap(dict):
    """A lap with only the data that the steering analysis reads."""

    def __init__(self, driver: str, lap_number: int):
        super().__init__(
            Driver=driver,
            LapNumber=lap_number,
            LapTime=pd.to_timedelta(92.0, unit="s"),
        )
        angles = np.linspace(0.0, 2 * np.pi, 240)
        self.telemetry = pd.DataFrame(
            {
                "Distance": np.linspace(0.0, 5000.0, 240),
                "Time": pd.to_timedelta(np.linspace(0.0, 92.0, 240), unit="s"),
                "X": 300.0 * np.cos(angles),
                "Y": 300.0 * np.sin(angles),
            }
        )

    def get_telemetry(self):
        return self.telemetry


def _use_lap(monkeypatch, lap: FakeLap) -> None:
    monkeypatch.setattr(
        analysis,
        "_lap",
        lambda session, driver=None, lap_number=None: lap,
    )


def test_steering_input_returns_a_normalized_envelope(monkeypatch):
    _use_lap(monkeypatch, FakeLap("VER", 12))
    envelope = analysis.steering_input(object(), "VER")
    assert envelope["kind"] == "telemetry"
    assert envelope["x"]["name"] == "distance"
    assert envelope["meta"]["channel"] == "Steering input"
    assert envelope["meta"]["unit"] == "%"
    assert envelope["meta"]["estimate"] == "from the X and Y positions"
    assert envelope["meta"]["positive"] == "left"
    assert envelope["meta"]["negative"] == "right"
    assert envelope["meta"]["driver"] == "VER"
    assert envelope["meta"]["lap"] == 12
    assert envelope["series"][0]["label"] == "VER L12"
    values = np.array([value for value in envelope["series"][0]["values"] if value is not None])
    assert values.size > 100
    assert values.min() >= -100.0
    assert values.max() <= 100.0
    middle = values[values.size // 10 : -values.size // 10]
    assert np.allclose(middle, 100.0)


def test_steering_input_on_a_time_axis(monkeypatch):
    _use_lap(monkeypatch, FakeLap("VER", 12))
    envelope = analysis.steering_input(object(), "VER", axis="time")
    assert envelope["x"]["name"] == "time"
    assert envelope["x"]["unit"] == "s"


def test_telemetry_accepts_the_steering_channel(monkeypatch):
    _use_lap(monkeypatch, FakeLap("HAM", 8))
    envelope = analysis.telemetry(object(), "HAM", channel="SteeringInput")
    assert envelope["meta"]["channel"] == "SteeringInput"
    assert envelope["meta"]["unit"] == "%"
    assert envelope["series"][0]["label"] == "HAM L8"


def test_compare_accepts_the_steering_channel(monkeypatch):
    laps = {"VER": FakeLap("VER", 12), "HAM": FakeLap("HAM", 13)}
    monkeypatch.setattr(
        analysis,
        "_lap",
        lambda session, driver=None, lap_number=None: laps[driver],
    )
    envelope = analysis.compare(
        object(),
        refs=[{"driver": "VER", "lap": 12}, {"driver": "HAM", "lap": 13}],
        channel="SteeringInput",
    )
    labels = [series["label"] for series in envelope["series"]]
    assert labels[0] == "VER L12"
    assert labels[1] == "HAM L13"
    assert labels[2].startswith("Delta")
    assert envelope["meta"]["unit"] == "%"
