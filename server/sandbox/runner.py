"""Run one registered function in a sandboxed subprocess.

This module is the entry point of a child process. Generated code cannot
import it. The parent process adds the limits: wall timeout, memory, and CPU.
This module sets the resource limits for itself.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import math
import resource
import traceback
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

MEMORY_BYTES = 2 * 1024**3
CPU_SECONDS = 150
FILE_SIZE_BYTES = 256 * 1024**2


def set_limits() -> None:
    """Set hard resource limits for this process."""
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_SIZE_BYTES, FILE_SIZE_BYTES))


def jsonable(value):
    """Convert numpy and pandas values to JSON-safe Python values."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, pd.Timedelta):
        return value.total_seconds()
    if isinstance(value, pd.Series):
        return jsonable(value.tolist())
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is pd.NaT:
        return None
    if isinstance(value, (dt.datetime, dt.timedelta)):
        return str(value)
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def load_session(ref: dict | None):
    """Load the requested FastF1 session. Return None without a reference."""
    if not ref:
        return None
    import fastf1

    from server.config import CACHE_DIR

    fastf1.Cache.enable_cache(str(CACHE_DIR))
    session = fastf1.get_session(int(ref["year"]), int(ref["round"]), str(ref["code"]))
    session.load(telemetry=bool(ref.get("telemetry", True)), weather=False, messages=False)
    return session


def load_module(path: Path):
    """Load the registered function from one file."""
    spec = importlib.util.spec_from_file_location("registered_analysis", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the registered module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "build", None)):
        raise RuntimeError("the module has no callable build function")
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one registered analysis function.")
    parser.add_argument("--file", required=True, help="path to the function file")
    parser.add_argument("--input", required=True, help="path to the input JSON file")
    parser.add_argument("--output", required=True, help="path to the result JSON file")
    args = parser.parse_args()

    set_limits()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    session = load_session(payload.get("session"))
    context = {"session": session, "params": payload.get("params", {})}
    module = load_module(Path(args.file))
    result = module.build(context)
    Path(args.output).write_text(json.dumps(jsonable(result), allow_nan=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
    except BaseException:
        traceback.print_exc()
        exit_code = 1
    raise SystemExit(exit_code)
