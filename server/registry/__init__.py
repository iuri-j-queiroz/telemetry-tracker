"""Store and run registered analysis functions.

The server is the authority for this directory. The builder only proposes code.
Registration is refused without a valid token and a passed validation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from server.config import ROOT, RUN_TIMEOUT_S
from server.sandbox.validate import validate_source
from server.schemas import validate_envelope

GENERATED_DIR = Path(__file__).resolve().parent / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
FUNCTION_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,60}$")


class RegistrationError(Exception):
    """The function did not pass registration."""


class RunError(Exception):
    """The function failed during a run."""


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not slug or not slug[0].isalpha():
        slug = f"analysis_{slug}" if slug else "analysis"
    return slug[:48]


def list_functions() -> list[dict]:
    """Return the metadata of all registered functions, newest first."""
    functions = []
    for path in sorted(GENERATED_DIR.glob("*.json")):
        try:
            functions.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    functions.sort(key=lambda item: item.get("created", ""), reverse=True)
    return functions


def get_function(function_id: str) -> dict | None:
    """Return the metadata of one function. None if unknown."""
    if not FUNCTION_ID_RE.match(function_id):
        return None
    path = GENERATED_DIR / f"{function_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def register(instruction: str, source: str, meta: dict | None = None) -> dict:
    """Validate one function and store it. Returns the metadata.

    Registration is idempotent: the same source returns the same function id.
    """
    errors = validate_source(source)
    if errors:
        raise RegistrationError("validation failed: " + "; ".join(errors))
    meta = meta or {}
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    slug = _slug(str(meta.get("name") or instruction or "analysis"))
    function_id = f"{slug}_{digest[:8]}"
    metadata_path = GENERATED_DIR / f"{function_id}.json"
    if metadata_path.exists():
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    (GENERATED_DIR / f"{function_id}.py").write_text(source, encoding="utf-8")
    metadata = {
        "id": function_id,
        "created": datetime.now(UTC).isoformat(),
        "instruction": instruction,
        "sha256": digest,
        "meta": meta,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def run(
    function_id: str,
    params: dict | None = None,
    session: dict | None = None,
    timeout_s: int | None = None,
) -> dict:
    """Run one registered function in the sandbox. Returns the envelope."""
    metadata = get_function(function_id)
    if metadata is None:
        raise RunError(f"unknown function: {function_id}")
    function_path = GENERATED_DIR / f"{function_id}.py"
    if not function_path.exists():
        raise RunError(f"the function file is missing: {function_id}")
    timeout = timeout_s or RUN_TIMEOUT_S
    with tempfile.TemporaryDirectory(prefix="tt-run-") as tmp:
        input_path = Path(tmp) / "input.json"
        output_path = Path(tmp) / "output.json"
        input_path.write_text(
            json.dumps({"params": params or {}, "session": session}), encoding="utf-8"
        )
        command = [
            sys.executable,
            "-m",
            "server.sandbox.runner",
            "--file",
            str(function_path),
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ]
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy(),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RunError(f"the function timed out after {timeout} s") from exc
        if completed.returncode != 0:
            lines = (completed.stderr or completed.stdout or "").strip().splitlines()
            tail = " | ".join(lines[-3:]) if lines else "unknown error"
            raise RunError(f"the function failed: {tail}")
        if not output_path.exists():
            raise RunError("the function produced no output")
        result = json.loads(output_path.read_text(encoding="utf-8"))
    errors = validate_envelope(result)
    if errors:
        raise RunError("envelope validation failed: " + "; ".join(errors))
    return result
