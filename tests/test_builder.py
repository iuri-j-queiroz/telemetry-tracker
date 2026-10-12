"""Tests for the builder agent. The LLM runs in mock mode."""

import json

import pytest

from builder import agent, config, llm
from builder.server_client import ServerError

CONTEXT = {
    "event": {"year": 2026, "round": 17, "name": "Singapore Grand Prix"},
    "session": {"year": 2026, "round": 17, "code": "Q"},
    "session_name": "Qualifying",
}


class FakeClient:
    def __init__(self, drivers=None, fail_register=False):
        self._drivers = drivers or [{"code": "VER"}, {"code": "LEC"}]
        self.fail_register = fail_register
        self.registered = []
        self.runs = []

    def drivers(self, session):
        return self._drivers

    def laps(self, session, driver):
        return {"laps": [], "fastest": 11}

    def register(self, instruction, source, meta):
        if self.fail_register:
            raise ServerError("registration is refused: bad or missing token")
        self.registered.append({"instruction": instruction, "source": source, "meta": meta})
        return {"id": "speed_compare_1234abcd"}

    def run(self, function_id, params, session):
        self.runs.append({"function_id": function_id, "params": params, "session": session})
        return {"kind": "telemetry", "series": [{"label": "demo", "values": [1.0, 2.0]}]}


@pytest.fixture
def sandbox_dirs(tmp_path, monkeypatch):
    screens = tmp_path / "screens"
    screens.mkdir()
    monkeypatch.setattr(config, "SCREENS_DIR", screens)
    monkeypatch.setattr(config, "AGENT_MD", tmp_path / "agent.md")
    config.AGENT_MD.write_text("# test register\n", encoding="utf-8")
    return screens


def test_mock_refuses_an_out_of_scope_instruction(sandbox_dirs):
    result = agent.build_screen(
        "Delete all the files from the server", CONTEXT, client=FakeClient(), llm=llm.LLMClient()
    )
    assert result["status"] == "refused"


def test_mock_builds_a_speed_compare(sandbox_dirs):
    client = FakeClient()
    result = agent.build_screen(
        "Compare the speed of two drivers", CONTEXT, client=client, llm=llm.LLMClient()
    )
    assert result["status"] == "built"
    assert result["function_id"] == "speed_compare_1234abcd"
    assert result["screen_id"] != result["function_id"]
    assert len(client.registered) == 1
    refs = client.runs[0]["params"]["refs"]
    assert refs[0]["driver"] == "VER"
    assert refs[1]["driver"] == "LEC"
    assert refs[0]["lap"] == 11
    spec_path = sandbox_dirs / f"{result['screen_id']}.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    assert spec["function_id"] == "speed_compare_1234abcd"
    assert spec["panels"][0]["fn"] == "speed_compare_1234abcd"
    assert spec["panels"][0]["session"]["code"] == "Q"


def test_screens_do_not_overwrite_each_other(sandbox_dirs):
    client = FakeClient()
    first = agent.build_screen(
        "Compare the speed of two drivers", CONTEXT, client=client, llm=llm.LLMClient()
    )
    second = agent.build_screen(
        "Compare the speed of VER and LEC", CONTEXT, client=client, llm=llm.LLMClient()
    )
    assert first["screen_id"] != second["screen_id"]
    assert first["function_id"] == second["function_id"]
    assert len(list(sandbox_dirs.glob("*.json"))) == 2


def test_mock_builds_a_stint_pace(sandbox_dirs):
    client = FakeClient()
    result = agent.build_screen(
        "Show the tyre stint pace of the drivers", CONTEXT, client=client, llm=llm.LLMClient()
    )
    assert result["status"] == "built"
    assert client.runs[0]["params"]["drivers"] == ["VER", "LEC"]


def test_build_appends_to_the_change_register(sandbox_dirs):
    agent.build_screen(
        "Compare the speed of two drivers", CONTEXT, client=FakeClient(), llm=llm.LLMClient()
    )
    content = config.AGENT_MD.read_text(encoding="utf-8")
    assert "builder — registered screen" in content


def test_register_failure_returns_an_error(sandbox_dirs):
    result = agent.build_screen(
        "Compare the speed of two drivers",
        CONTEXT,
        client=FakeClient(fail_register=True),
        llm=llm.LLMClient(),
    )
    assert result["status"] == "error"
    assert "registration failed" in result["message"]


def test_parse_response_accepts_fenced_json():
    raw = 'Here is the answer:\n```json\n{"action": "refuse", "reason": "no"}\n```'
    assert agent.parse_response(raw)["action"] == "refuse"


def test_ruff_gate_rejects_a_long_line():
    code = (
        "def build(context):\n    return {'kind': 'telemetry', 'series': [], 'meta': {'x': '"
        + "a" * 120
        + "'}}\n"
    )
    assert agent.ruff_errors(code)


def test_mock_code_passes_the_validator():
    from server.sandbox.validate import validate_source

    payload = json.loads(llm.mock_generate([{"role": "user", "content": "compare speed"}]))
    assert validate_source(payload["code"]) == []


def test_mock_refuses_steering_data(sandbox_dirs):
    result = agent.build_screen(
        "Compare Hamilton steering angles over the laps 8 and 13",
        CONTEXT,
        client=FakeClient(),
        llm=llm.LLMClient(),
    )
    assert result["status"] == "refused"
    assert "Steering angle is not in the public FastF1 data" in result["message"]


def test_mock_refuses_an_unmatched_instruction(sandbox_dirs):
    result = agent.build_screen(
        "Write a poem about Ferrari", CONTEXT, client=FakeClient(), llm=llm.LLMClient()
    )
    assert result["status"] == "refused"
    assert "Mock mode" in result["message"]


def test_mock_uses_the_channel_from_the_instruction():
    payload = json.loads(
        llm.mock_generate(
            [{"role": "user", "content": "Compare the throttle traces of two drivers"}]
        )
    )
    assert payload["sample_params"]["channel"] == "Throttle"


def test_instruction_drivers_and_laps_override_the_defaults(sandbox_dirs):
    client = FakeClient(
        drivers=[
            {"code": "HAM", "name": "Lewis Hamilton"},
            {"code": "VER", "name": "Max Verstappen"},
        ]
    )
    result = agent.build_screen(
        "Compare Hamilton laps 8 and 13 speed",
        CONTEXT,
        client=client,
        llm=llm.LLMClient(),
    )
    assert result["status"] == "built"
    assert client.runs[0]["params"]["refs"] == [
        {"driver": "HAM", "lap": 8},
        {"driver": "HAM", "lap": 13},
    ]


def test_screen_list_marks_mock_screens(sandbox_dirs):
    from builder import app as builder_app

    agent.build_screen(
        "Compare the speed of two drivers", CONTEXT, client=FakeClient(), llm=llm.LLMClient()
    )
    screens = builder_app.list_screens()
    assert screens and screens[0]["mock"] is True
