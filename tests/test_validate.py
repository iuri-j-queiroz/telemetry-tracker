"""Tests for the AST whitelist validator."""

from server.sandbox.validate import validate_source

GOOD_SOURCE = """
import numpy as np
from server.normalize import envelope

CHANNEL = "Speed"


def build(context):
    params = context.get("params", {})
    values = np.array([1.0, 2.0, 3.0])
    return envelope(
        "telemetry",
        series=[{"label": "demo", "values": values.tolist()}],
        meta=params,
    )
"""


def test_good_source_passes():
    assert validate_source(GOOD_SOURCE) == []


def test_import_of_os_is_refused():
    errors = validate_source("import os\n\ndef build(context):\n    return {}\n")
    assert any("not allowed" in error for error in errors)


def test_import_of_subprocess_is_refused():
    source = "from subprocess import run\n\ndef build(context):\n    return {}\n"
    assert validate_source(source)


def test_import_of_server_registry_is_refused():
    source = "import server.registry\n\ndef build(context):\n    return {}\n"
    assert validate_source(source)


def test_call_of_open_is_refused():
    source = "def build(context):\n    return open('x')\n"
    assert any("open" in error for error in validate_source(source))


def test_call_of_eval_is_refused():
    source = "def build(context):\n    return eval('1')\n"
    assert any("eval" in error for error in validate_source(source))


def test_dunder_import_is_refused():
    source = "def build(context):\n    return __import__('os')\n"
    assert validate_source(source)


def test_dunder_attribute_is_refused():
    source = "import numpy as np\n\ndef build(context):\n    return np.__version__\n"
    assert validate_source(source)


def test_private_attribute_is_refused():
    source = "def build(context):\n    return context._secret\n"
    assert validate_source(source)


def test_attribute_assignment_is_refused():
    source = "def build(context):\n    context.run = 1\n    return {}\n"
    assert validate_source(source)


def test_module_level_call_is_refused():
    source = "print('hello')\n\ndef build(context):\n    return {}\n"
    assert any("module level" in error for error in validate_source(source))


def test_build_function_is_required():
    errors = validate_source("import numpy as np\n")
    assert any("build" in error for error in errors)


def test_two_build_functions_are_refused():
    source = "def build(context):\n    return {}\n\ndef build(context):\n    return {}\n"
    errors = validate_source(source)
    assert any("only one" in error for error in errors)


def test_decorators_are_refused():
    source = "def wrap(fn):\n    return fn\n\n@wrap\ndef build(context):\n    return {}\n"
    errors = validate_source(source)
    assert any("decorators" in error for error in errors)


def test_varargs_are_refused():
    source = "def build(*args):\n    return {}\n"
    errors = validate_source(source)
    assert any("args" in error for error in errors)


def test_build_without_parameter_is_refused():
    source = "def build():\n    return {}\n"
    errors = validate_source(source)
    assert any("parameter" in error for error in errors)


def test_syntax_error_is_reported():
    errors = validate_source("def build(context:\n")
    assert any("syntax error" in error for error in errors)


def test_empty_source_is_refused():
    assert validate_source("   ")
