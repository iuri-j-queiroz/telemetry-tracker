"""Tests for the registry store and the sandbox runner."""

import pytest

from server import registry

RUNNABLE_SOURCE = """
import numpy as np


def build(context):
    factor = float(context.get("params", {}).get("factor", 1.0))
    values = (np.array([1.0, 2.0, 3.0]) * factor).tolist()
    return {
        "kind": "telemetry",
        "x": {"name": "sample", "unit": "", "values": [0, 1, 2]},
        "series": [{"label": "demo", "values": values}],
        "meta": {"factor": factor},
    }
"""

BROKEN_SOURCE = """
import os


def build(context):
    return {}
"""


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "GENERATED_DIR", tmp_path)
    return registry


def test_register_refuses_a_bad_source(store):
    with pytest.raises(registry.RegistrationError):
        store.register("test", BROKEN_SOURCE)


def test_register_is_idempotent(store):
    first = store.register("demo analysis", RUNNABLE_SOURCE, {"name": "demo"})
    second = store.register("demo analysis", RUNNABLE_SOURCE, {"name": "demo"})
    assert first["id"] == second["id"]


def test_list_functions_returns_metadata(store):
    metadata = store.register("demo analysis", RUNNABLE_SOURCE, {"name": "demo"})
    listed = store.list_functions()
    assert [item["id"] for item in listed] == [metadata["id"]]


def test_run_returns_the_envelope(store):
    metadata = store.register("demo analysis", RUNNABLE_SOURCE, {"name": "demo"})
    envelope = store.run(metadata["id"], params={"factor": 2.0})
    assert envelope["kind"] == "telemetry"
    assert envelope["series"][0]["values"] == [2.0, 4.0, 6.0]


def test_run_refuses_an_unknown_function(store):
    with pytest.raises(registry.RunError):
        store.run("does_not_exist", params={})
