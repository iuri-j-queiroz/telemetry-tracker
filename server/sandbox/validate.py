"""AST whitelist validation for generated analysis code.

This module is the single source of truth for code safety.
The builder imports it. The server runs it again before registration.
See agent.md, section 5.
"""

from __future__ import annotations

import ast
from pathlib import Path

ALLOWED_IMPORT_ROOTS = {"fastf1", "numpy", "pandas", "matplotlib"}
ALLOWED_EXACT_MODULES = {"server.normalize"}

BANNED_NAMES = {
    "exec",
    "eval",
    "compile",
    "open",
    "input",
    "breakpoint",
    "__import__",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "exit",
    "quit",
    "memoryview",
}

BANNED_ATTRS = {
    "system",
    "popen",
    "spawn",
    "spawnl",
    "spawnlp",
    "spawnv",
    "spawnvp",
    "fork",
    "execv",
    "execve",
    "execvp",
    "kill",
    "killpg",
    "setuid",
    "setgid",
    "chmod",
    "chown",
    "unlink",
    "rmtree",
    "removedirs",
}

MAX_SOURCE_BYTES = 50_000


class _Validator(ast.NodeVisitor):
    def __init__(self) -> None:
        self.errors: list[str] = []

    def _error(self, node: ast.AST, message: str) -> None:
        line = getattr(node, "lineno", "?")
        self.errors.append(f"line {line}: {message}")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_module(alias.name, node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is None:
            self._error(node, "relative imports are not allowed")
            return
        if any(alias.name == "*" for alias in node.names):
            self._error(node, "star imports are not allowed")
            return
        self._check_module(node.module, node)
        self.generic_visit(node)

    def _check_module(self, module: str, node: ast.AST) -> None:
        if module in ALLOWED_EXACT_MODULES:
            return
        if module.split(".")[0] not in ALLOWED_IMPORT_ROOTS:
            self._error(node, f"import of {module} is not allowed")

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in BANNED_NAMES:
            self._error(node, f"use of {node.id} is not allowed")
        elif node.id.startswith("__"):
            self._error(node, f"dunder name {node.id} is not allowed")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_") or node.attr in BANNED_ATTRS:
            self._error(node, f"attribute {node.attr} is not allowed")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Attribute):
                self._error(node, "attribute assignment is not allowed")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Attribute):
            self._error(node, "attribute assignment is not allowed")
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Attribute):
            self._error(node, "attribute assignment is not allowed")
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            if isinstance(target, ast.Attribute):
                self._error(node, "attribute delete is not allowed")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._error(node, "class definitions are not allowed")

    def visit_Global(self, node: ast.Global) -> None:
        self._error(node, "global is not allowed")

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self._error(node, "nonlocal is not allowed")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._error(node, "async functions are not allowed")

    def visit_Await(self, node: ast.Await) -> None:
        self._error(node, "await is not allowed")


def _check_module_level(tree: ast.Module) -> list[str]:
    errors = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.FunctionDef):
            continue
        if isinstance(node, ast.Assign) and all(
            isinstance(target, ast.Name) for target in node.targets
        ):
            continue
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        errors.append(
            f"line {getattr(node, 'lineno', '?')}: "
            "only imports, functions, and constant assignments are allowed at module level"
        )
    builds = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build"]
    if not builds:
        errors.append("one top-level function named 'build' is required")
    elif len(builds) > 1:
        errors.append("only one top-level function named 'build' is allowed")
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.decorator_list:
            errors.append(f"line {node.lineno}: decorators are not allowed")
        args = node.args
        if args.vararg or args.kwarg:
            errors.append(f"line {node.lineno}: *args and **kwargs are not allowed")
        if node.name == "build" and not (args.posonlyargs or args.args):
            errors.append("build must take one parameter: the context")
    return errors


def validate_source(source: str) -> list[str]:
    """Return a list of validation errors. An empty list means the code is allowed."""
    if not isinstance(source, str) or not source.strip():
        return ["source is empty"]
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        return [f"source is larger than {MAX_SOURCE_BYTES} bytes"]
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"syntax error: {exc}"]
    errors = _check_module_level(tree)
    validator = _Validator()
    validator.visit(tree)
    errors.extend(validator.errors)
    return list(dict.fromkeys(errors))


def validate_file(path: str | Path) -> list[str]:
    """Read one file and validate the source."""
    return validate_source(Path(path).read_text(encoding="utf-8"))
