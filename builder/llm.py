"""LLM client for the builder. OpenAI-compatible, with a mock mode.

The mock mode returns known-good analyses. It lets the full system run
without an API key. See agent.md, section 2.
"""

from __future__ import annotations

import json
import re

from builder import config

REFUSE_WORDS = (
    "delete",
    "remove file",
    "scrape",
    "hack",
    "password",
    "malware",
    "shell",
    "subprocess",
    "os.",
    "email",
    "website",
    "http://",
    "https://",
)

STINT_WORDS = ("stint", "tyre", "tire", "compound", "degradation", "pace")

COMPARE_WORDS = ("compare", "speed", "versus", "vs", "delta", "gap", "difference", "telemetry")

STEERING_WORDS = ("steering", "steering wheel", "steering input", "steering angle")

# Requests that public FastF1 data cannot answer. Never fake this data.
UNAVAILABLE_DATA = {
    "tyre temp": (
        "Tyre temperature is not in the public FastF1 data. "
        "The channels are Speed, Throttle, Brake, nGear, RPM, and DRS."
    ),
    "tire temp": (
        "Tyre temperature is not in the public FastF1 data. "
        "The channels are Speed, Throttle, Brake, nGear, RPM, and DRS."
    ),
    "tyre pressure": (
        "Tyre pressure is not in the public FastF1 data. "
        "The channels are Speed, Throttle, Brake, nGear, RPM, and DRS."
    ),
    "tire pressure": (
        "Tyre pressure is not in the public FastF1 data. "
        "The channels are Speed, Throttle, Brake, nGear, RPM, and DRS."
    ),
    "g-force": "G-force is not in the public FastF1 data.",
    "g force": "G-force is not in the public FastF1 data.",
    "suspension": "Suspension data is not in the public FastF1 data.",
    "brake temperature": "Brake temperature is not in the public FastF1 data.",
}

MOCK_LIMITATION = (
    "Mock mode builds only three example analyses: a driver speed compare, a stint pace chart, "
    "and a steering input trace. "
    "Set LLM_MOCK=0 and fill the LLM_* values in .env for free-form building."
)

MOCK_STEERING_CODE = """
from fastf1 import plotting

from server.normalize import normalize_length, steering_input


def build(context):
    session = context["session"]
    params = context.get("params", {})
    refs = params.get("refs", [])
    streams = {}
    colors = {}
    for ref in refs:
        laps = session.laps.pick_drivers(str(ref["driver"])).pick_laps(int(ref["lap"]))
        lap = laps.pick_fastest()
        if lap is None:
            lap = laps.pick_fastest(only_by_time=True)
        if lap is None:
            raise ValueError(
                "no lap data for " + str(ref["driver"]) + " lap " + str(ref["lap"])
            )
        telemetry = lap.get_telemetry()
        if "Distance" not in telemetry.columns:
            telemetry = telemetry.add_distance()
        label = str(lap["Driver"]) + " L" + str(int(lap["LapNumber"]))
        streams[label] = (
            telemetry["Distance"].to_numpy(dtype=float),
            steering_input(telemetry["X"], telemetry["Y"]),
        )
        try:
            colors[label] = str(plotting.get_driver_color(str(lap["Driver"]), session=session))
        except Exception:
            colors[label] = "#ffffff"
    result = normalize_length(
        streams, "SteeringInput", step_m=float(params.get("step_m", 10))
    )
    for series in result["series"]:
        series["color"] = colors.get(series["label"], "#ffffff")
    result["meta"]["unit"] = "%"
    result["meta"]["positive"] = "left"
    result["meta"]["negative"] = "right"
    result["meta"]["estimate"] = "from the X and Y positions"
    return result
"""

MOCK_COMPARE_CODE = """
from fastf1 import plotting

from server.normalize import normalize_length


def build(context):
    session = context["session"]
    params = context.get("params", {})
    refs = params.get("refs", [])
    channel = str(params.get("channel", "Speed"))
    streams = {}
    colors = {}
    for ref in refs:
        laps = session.laps.pick_drivers(str(ref["driver"])).pick_laps(int(ref["lap"]))
        lap = laps.pick_fastest()
        if lap is None:
            lap = laps.pick_fastest(only_by_time=True)
        if lap is None:
            raise ValueError(
                "no lap data for " + str(ref["driver"]) + " lap " + str(ref["lap"])
            )
        telemetry = lap.get_telemetry()
        if "Distance" not in telemetry.columns:
            telemetry = telemetry.add_distance()
        label = str(lap["Driver"]) + " L" + str(int(lap["LapNumber"]))
        streams[label] = (
            telemetry["Distance"].to_numpy(dtype=float),
            telemetry[channel].to_numpy(dtype=float),
        )
        try:
            colors[label] = str(plotting.get_driver_color(str(lap["Driver"]), session=session))
        except Exception:
            colors[label] = "#ffffff"
    result = normalize_length(streams, channel, step_m=float(params.get("step_m", 10)))
    for series in result["series"]:
        series["color"] = colors.get(series["label"], "#ffffff")
    if len(result["series"]) == 2:
        first = result["series"][0]["values"]
        second = result["series"][1]["values"]
        delta = []
        for index in range(len(first)):
            left = first[index]
            right = second[index]
            delta.append(None if left is None or right is None else right - left)
        result["series"].append(
            {"label": "Delta", "values": delta, "color": "#ffffff", "dash": True}
        )
    return result
"""

MOCK_STINT_CODE = """
from server.normalize import envelope


def build(context):
    session = context["session"]
    params = context.get("params", {})
    drivers = [str(code) for code in params.get("drivers", [])]
    labels = []
    values = []
    for code in drivers:
        laps = session.laps.pick_drivers(code)
        laps = laps[laps["Stint"].notna()]
        for stint, group in laps.groupby("Stint"):
            times = group["LapTime"].dropna().dt.total_seconds()
            if times.empty:
                continue
            labels.append(code + " S" + str(int(stint)))
            values.append(round(float(times.mean()), 3))
    return envelope(
        "barchart",
        x={"name": "stint", "unit": "", "values": labels},
        series=[{"label": "Mean lap time", "values": values}],
        meta={"unit": "s", "mode": "stint pace"},
    )
"""

MOCK_COMPARE_PARAMS = {
    "refs": [
        {"driver": "auto1", "lap": "fastest"},
        {"driver": "auto2", "lap": "fastest"},
    ],
    "channel": "Speed",
    "step_m": 10,
}

MOCK_STINT_PARAMS = {"drivers": ["auto1", "auto2"]}

MOCK_STEERING_PARAMS = {
    "refs": [
        {"driver": "auto1", "lap": "fastest"},
        {"driver": "auto2", "lap": "fastest"},
    ],
    "step_m": 10,
}


class LLMError(Exception):
    """The LLM did not answer with usable output."""


class LLMClient:
    def __init__(self) -> None:
        self.mock = config.LLM_MOCK
        self._client = None

    def generate(self, messages: list[dict]) -> str:
        if self.mock:
            return mock_generate(messages)
        from openai import OpenAI

        if self._client is None:
            self._client = OpenAI(
                base_url=config.LLM_BASE_URL,
                api_key=config.LLM_API_KEY or "not-needed",
                timeout=120,
            )
        response = self._client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=messages,
            temperature=0.2,
        )
        content = response.choices[0].message.content
        if not content:
            raise LLMError("the model returned an empty answer")
        return content


def _first_user_text(messages: list[dict]) -> str:
    for message in messages:
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


def _contains_word(text: str, word: str) -> bool:
    """Match a whole word. 'gap' must not match inside 'Singapore'."""
    tail = r"\b" if word[-1:].isalnum() else ""
    return re.search(rf"\b{re.escape(word)}{tail}", text) is not None


def _matches_any(text: str, words: tuple[str, ...]) -> bool:
    return any(_contains_word(text, word) for word in words)


def _mock_channel(text: str) -> str:
    """Pick the trace channel from the instruction text."""
    for name in ("Throttle", "Brake", "RPM", "nGear", "DRS", "Speed"):
        if name.lower() in text:
            return name
    if "gear" in text:
        return "nGear"
    return "Speed"


def mock_generate(messages: list[dict]) -> str:
    """Return one known-good answer. Select the answer by keyword.

    The mock refuses requests it cannot serve. It never substitutes one
    analysis for another.
    """
    text = _first_user_text(messages).lower()
    if _matches_any(text, REFUSE_WORDS):
        return json.dumps(
            {
                "action": "refuse",
                "reason": (
                    "The builder only builds FastF1 data analyses. "
                    "This request is outside the allowed scope."
                ),
            }
        )
    for term, reason in UNAVAILABLE_DATA.items():
        if _contains_word(text, term):
            return json.dumps({"action": "refuse", "reason": reason})
    if _matches_any(text, STEERING_WORDS):
        return json.dumps(
            {
                "action": "build",
                "name": "steering_input",
                "title": "Steering input",
                "code": MOCK_STEERING_CODE,
                "sample_params": MOCK_STEERING_PARAMS,
            }
        )
    if _matches_any(text, STINT_WORDS):
        return json.dumps(
            {
                "action": "build",
                "name": "stint_pace",
                "title": "Stint pace",
                "code": MOCK_STINT_CODE,
                "sample_params": MOCK_STINT_PARAMS,
            }
        )
    if _matches_any(text, COMPARE_WORDS):
        params = dict(MOCK_COMPARE_PARAMS)
        params["channel"] = _mock_channel(text)
        return json.dumps(
            {
                "action": "build",
                "name": "speed_compare",
                "title": "Speed compare",
                "code": MOCK_COMPARE_CODE,
                "sample_params": params,
            }
        )
    return json.dumps({"action": "refuse", "reason": MOCK_LIMITATION})
