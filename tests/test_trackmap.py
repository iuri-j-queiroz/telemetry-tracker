"""Tests for the track map layers. No FastF1 network access."""

import numpy as np
import pandas as pd

from server import analysis


class FakeLap(dict):
    """A lap with the channels that the track map reads."""

    def __init__(self, driver: str = "VER", lap_number: int = 12):
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
                "SessionTime": pd.to_timedelta(np.linspace(1000.0, 1092.0, 240), unit="s"),
                "X": 300.0 * np.cos(angles),
                "Y": 300.0 * np.sin(angles),
                "Speed": np.linspace(280.0, 90.0, 240),
                "Throttle": np.linspace(100.0, 0.0, 240),
                "Brake": np.linspace(0.0, 100.0, 240),
            }
        )

    def get_telemetry(self):
        return self.telemetry


class FakeSession:
    name = "Race"

    def __init__(self):
        positions = np.linspace(0.0, 2000.0, 400)
        self.pos_data = {
            "44": pd.DataFrame(
                {
                    "Time": pd.to_timedelta(np.linspace(1000.0, 1200.0, 400), unit="s"),
                    "X": positions,
                    "Y": positions / 2.0,
                }
            )
        }


class FakeQualiSession(FakeSession):
    name = "Qualifying"


def _use_lap(monkeypatch, lap: FakeLap) -> None:
    monkeypatch.setattr(
        analysis,
        "_lap",
        lambda session, driver=None, lap_number=None: lap,
    )


def _use_drivers(monkeypatch) -> None:
    monkeypatch.setattr(
        analysis,
        "list_drivers",
        lambda session: [
            {"code": "VER", "number": "3", "color": "#000011"},
            {"code": "HAM", "number": "44", "color": "#000022"},
        ],
    )


def test_trackmap_carries_the_input_channels(monkeypatch):
    _use_lap(monkeypatch, FakeLap("VER", 12))
    envelope = analysis.trackmap(object(), "VER", step_m=50.0)
    channels = envelope["meta"]["channels"]
    assert set(channels) >= {"Speed", "Throttle", "Brake", "SteeringInput"}
    count = len(envelope["series"][0]["x"])
    assert count > 0
    for values in channels.values():
        assert len(values) == count
    steering = [value for value in channels["SteeringInput"] if value is not None]
    assert min(steering) >= -100.0
    assert max(steering) <= 100.0


def test_trackmap_has_no_others_outside_a_race(monkeypatch):
    _use_lap(monkeypatch, FakeLap("VER", 12))
    _use_drivers(monkeypatch)
    envelope = analysis.trackmap(FakeQualiSession(), "VER", step_m=100.0)
    assert "others" not in envelope["meta"]


def test_trackmap_shows_the_other_drivers_in_a_race(monkeypatch):
    _use_lap(monkeypatch, FakeLap("VER", 12))
    _use_drivers(monkeypatch)
    envelope = analysis.trackmap(FakeSession(), "VER", step_m=100.0)
    others = envelope["meta"]["others"]
    assert [other["label"] for other in others] == ["HAM"]
    count = len(envelope["series"][0]["x"])
    assert len(others[0]["x"]) == count
    assert all(value is not None for value in others[0]["x"])


def test_trackmap_keeps_the_selected_driver_out_of_others(monkeypatch):
    _use_lap(monkeypatch, FakeLap("HAM", 30))
    _use_drivers(monkeypatch)
    envelope = analysis.trackmap(FakeSession(), "HAM", step_m=100.0)
    labels = [other["label"] for other in envelope["meta"]["others"]]
    assert "HAM" not in labels
