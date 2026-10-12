"""Tests for the envelope schema."""

from server.schemas import validate_envelope


def test_valid_envelope_passes():
    envelope = {
        "kind": "telemetry",
        "x": {"name": "distance", "unit": "m", "values": [0, 5]},
        "series": [{"label": "VER", "values": [1.0, 2.0]}],
        "meta": {},
    }
    assert validate_envelope(envelope) == []


def test_image_envelope_passes_without_series():
    envelope = {"kind": "image", "data_base64": "abc", "mime": "image/png"}
    assert validate_envelope(envelope) == []


def test_envelope_without_series_or_image_fails():
    assert validate_envelope({"kind": "telemetry"})


def test_non_dict_fails():
    assert validate_envelope([1, 2, 3])


def test_series_without_label_fails():
    envelope = {"kind": "telemetry", "series": [{"values": [1.0]}]}
    assert validate_envelope(envelope)
