"""Builder agent: instruction -> code -> validation -> registration -> screen.

The gate order comes from agent.md, section 2: AST validation, ruff check,
server re-validation, smoke test.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime

from builder import config
from builder.llm import LLMClient
from builder.prompts import SYSTEM_PROMPT, user_prompt
from builder.server_client import ServerClient, ServerError
from server.sandbox.validate import validate_source
from server.schemas import validate_envelope


def parse_response(raw: str) -> dict:
    """Parse one LLM answer. Accept plain JSON and fenced JSON."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("the answer has no JSON object")
    return json.loads(text[start : end + 1])


def ruff_errors(code: str) -> list[str]:
    """Run the ruff check gate. Returns the errors, or an empty list."""
    command = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--output-format",
        "concise",
        "--stdin-filename",
        "analysis.py",
        "-",
    ]
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            command,
            input=code,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=config.ROOT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return [f"ruff could not run: {error}"]
    if completed.returncode == 0:
        return []
    return [line for line in completed.stdout.splitlines() if line.strip()][:10]


def resolve_params(params: dict, session: dict, client: ServerClient) -> dict:
    """Replace the placeholders auto1, auto2, and 'fastest' with real values."""
    resolved = json.loads(json.dumps(params or {}))
    drivers = client.drivers(session)
    codes = [str(driver["code"]) for driver in drivers if driver.get("code")]

    def code_for(token):
        if isinstance(token, str) and token.startswith("auto"):
            index = int(token[4:] or "1") - 1
            if 0 <= index < len(codes):
                return codes[index]
        return token

    def walk(value):
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item) for item in value]
        return code_for(value)

    resolved = walk(resolved)
    refs = resolved.get("refs", []) if isinstance(resolved, dict) else []
    for ref in refs:
        if isinstance(ref, dict) and str(ref.get("lap", "")) == "fastest":
            data = client.laps(session, str(ref.get("driver", "")))
            if data.get("fastest") is not None:
                ref["lap"] = data["fastest"]
    return resolved


LAP_PATTERN = re.compile(r"\blaps?\s*((?:\d+[\s,and&/]*)+)", re.IGNORECASE)


def instruction_refs(instruction: str, drivers: list[dict]) -> list[dict]:
    """Read driver codes and lap numbers from the instruction text.

    Returns one hint for each named driver and lap, in the text order.
    """
    text = instruction.lower()
    found: list[tuple[int, str]] = []
    for driver in drivers:
        code = str(driver.get("code", ""))
        name = str(driver.get("name", ""))
        positions = []
        if code:
            match = re.search(rf"\b{re.escape(code.lower())}\b", text)
            if match:
                positions.append(match.start())
        last_name = name.split(" ")[-1].lower() if name else ""
        if len(last_name) > 2:
            match = re.search(rf"\b{re.escape(last_name)}\b", text)
            if match:
                positions.append(match.start())
        if positions:
            found.append((min(positions), code))
    found.sort()
    driver_order: list[str] = []
    for _, code in found:
        if code not in driver_order:
            driver_order.append(code)
    lap_numbers: list[int] = []
    for group in LAP_PATTERN.findall(text):
        lap_numbers.extend(int(number) for number in re.findall(r"\d+", group))
    if not driver_order and not lap_numbers:
        return []
    hints: list[dict] = []
    if len(driver_order) >= 2:
        for index, code in enumerate(driver_order[:2]):
            lap = lap_numbers[index] if index < len(lap_numbers) else None
            hints.append({"driver": code, "lap": lap})
    elif len(driver_order) == 1:
        laps = lap_numbers[:2] or [None]
        hints = [{"driver": driver_order[0], "lap": lap} for lap in laps]
    else:
        hints = [{"driver": None, "lap": number} for number in lap_numbers[:2]]
    return hints


def apply_instruction_refs(params: dict, instruction: str, drivers: list[dict]) -> dict:
    """Override refs with the drivers and laps named in the instruction."""
    refs = params.get("refs") if isinstance(params, dict) else None
    if not isinstance(refs, list) or not refs:
        return params
    for index, hint in enumerate(instruction_refs(instruction, drivers)[: len(refs)]):
        ref = refs[index]
        if not isinstance(ref, dict):
            continue
        if hint.get("driver"):
            ref["driver"] = hint["driver"]
        if hint.get("lap") is not None:
            ref["lap"] = hint["lap"]
    return params


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"screen_{slug}" if slug else "screen"
    return slug[:40]


def screen_identity(title: str, instruction: str, session: dict, params: dict) -> str:
    """One stable id for the screen. Two equal requests share it.

    The function id comes from the code. The screen id comes from the request.
    Two screens can use one function with different parameters.
    """
    payload = json.dumps(
        {"instruction": instruction, "session": session, "params": params},
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]
    return f"{_slug(title or 'analysis')}_{digest}"


def save_screen(
    function_id: str,
    title: str,
    instruction: str,
    session: dict,
    params: dict,
    context: dict,
    mock: bool = False,
) -> dict:
    """Save the screen spec. The app renders the panels from the spec."""
    screen_id = screen_identity(title, instruction, session, params)
    spec = {
        "id": screen_id,
        "function_id": function_id,
        "title": title or function_id,
        "instruction": instruction,
        "created": datetime.now(UTC).isoformat(),
        "mock": mock,
        "context": {
            "event": context.get("event"),
            "session_name": context.get("session_name"),
        },
        "panels": [
            {
                "type": "registered",
                "fn": function_id,
                "title": title or function_id,
                "session": session,
                "params": params,
            }
        ],
    }
    path = config.SCREENS_DIR / f"{screen_id}.json"
    path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return spec


def append_change_entry(screen_id: str, function_id: str, title: str, instruction: str) -> None:
    """Add one audit entry to the agent.md Change Register."""
    stamp = datetime.now(UTC).date().isoformat()
    entry = (
        f"\n### [{stamp}] builder — registered screen `{screen_id}` (function `{function_id}`)\n"
        f"- **Files**: server/registry/generated/{function_id}.py, "
        f"server/registry/generated/{function_id}.json, builder/screens/{screen_id}.json\n"
        f'- **Change**: Built a screen for the instruction: "{instruction}"\n'
        "- **Checks**: AST validation, ruff check, server re-validation, smoke test passed\n"
        f"- **Decisions/notes**: Screen title: {title}\n"
    )
    try:
        existing = config.AGENT_MD.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            existing += "\n"
        config.AGENT_MD.write_text(existing + entry, encoding="utf-8")
    except OSError:
        pass  # the register is best-effort


def build_screen(
    instruction: str,
    context: dict,
    client: ServerClient | None = None,
    llm: LLMClient | None = None,
) -> dict:
    """Run the builder loop. Returns one result dict for the app."""
    client = client or ServerClient()
    llm = llm or LLMClient()
    mock = bool(getattr(llm, "mock", False))
    session = context.get("session") or {}
    if not session.get("year"):
        return {"status": "error", "message": "Select an event and a session first."}

    prompt_context = dict(context)
    drivers: list[dict] = []
    try:
        drivers = client.drivers(session)
        prompt_context["driver_codes"] = [str(d.get("code", "")) for d in drivers][:6]
    except ServerError:
        prompt_context["driver_codes"] = []

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt(instruction, prompt_context)},
    ]
    last_error = "the builder stopped without a result"

    def retry(reason: str, raw: str) -> None:
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": f"{reason} Fix the code and answer again."})

    for _attempt in range(config.MAX_ATTEMPTS):
        try:
            raw = llm.generate(messages)
        except Exception as error:  # noqa: BLE001 - report every LLM problem to the user
            return {"status": "error", "message": f"the LLM failed: {error}"}
        try:
            response = parse_response(raw)
        except (ValueError, json.JSONDecodeError) as error:
            last_error = f"the answer is not valid JSON: {error}"
            retry(f"{last_error}.", raw)
            continue
        if response.get("action") == "refuse":
            reason = str(response.get("reason", "This request is outside the allowed scope."))
            return {"status": "refused", "message": reason}
        code = response.get("code")
        if not isinstance(code, str) or not code.strip():
            last_error = "the answer has no code"
            retry(f"{last_error}.", raw)
            continue
        errors = validate_source(code) + ruff_errors(code)
        if errors:
            last_error = "validation failed: " + "; ".join(errors[:5])
            retry(f"{last_error}.", raw)
            continue

        name = str(response.get("name", "analysis"))
        title = str(response.get("title", name))
        try:
            metadata = client.register(instruction, code, {"name": name, "title": title})
        except ServerError as error:
            last_error = f"registration failed: {error}"
            break

        function_id = str(metadata["id"])
        try:
            raw_params = response.get("sample_params") or {}
            hinted = apply_instruction_refs(raw_params, instruction, drivers)
            params = resolve_params(hinted, session, client)
        except ServerError as error:
            return {"status": "error", "message": f"cannot prepare the test: {error}"}
        try:
            envelope = client.run(function_id, params, session)
        except ServerError as error:
            last_error = f"the smoke test failed: {error}"
            retry(f"{last_error}.", raw)
            continue
        envelope_errors = validate_envelope(envelope)
        if envelope_errors:
            last_error = "the output envelope is invalid: " + "; ".join(envelope_errors[:5])
            retry(f"{last_error}.", raw)
            continue

        spec = save_screen(function_id, title, instruction, session, params, context, mock=mock)
        screen_id = str(spec["id"])
        append_change_entry(screen_id, function_id, title, instruction)
        message = f"Screen '{title}' is ready."
        if mock:
            message += (
                " Mock mode: this is a canned example. Set LLM_MOCK=0 for free-form building."
            )
        return {
            "status": "built",
            "message": message,
            "screen_id": screen_id,
            "function_id": function_id,
            "mock": mock,
        }

    return {"status": "error", "message": last_error}
