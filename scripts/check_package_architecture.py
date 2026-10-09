"""Validate package composition and static dependencies without importing Apizr."""

import argparse
import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERIC_BUCKETS = {"utils", "helpers", "common", "services"}


def facade(target: str, kind: str) -> str:
    """The complete allowed forwarding shape; docstrings are immaterial."""
    if kind == "module":
        return f"""
import sys
import {target} as _implementation
from {target} import *
sys.modules[__name__] = _implementation
"""
    return f"""
from typing import Any
import {target} as _implementation
from {target} import *
def __getattr__(name: str) -> Any:
    return getattr(_implementation, name)
def __dir__() -> list[str]:
    return dir(_implementation)
"""


def shape(tree: ast.Module) -> str:
    if tree.body and isinstance(tree.body[0], ast.Expr):
        value = tree.body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            tree.body.pop(0)
    return ast.dump(tree, include_attributes=False)


def module_name(path: str) -> str:
    parts = list(Path(path).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(("apizr", *parts))


def imports(tree: ast.Module, path: str) -> set[str]:
    """Include relative, from-package and literal dynamic imports in any scope."""
    names: set[str] = set()
    package = module_name(path).split(".")
    if not path.endswith("/__init__.py") and path != "__init__.py":
        package.pop()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = ".".join((*package[: len(package) - node.level + 1], base))
                base = base.rstrip(".")
            names.add(base)
            names.update(base + "." + alias.name for alias in node.names)
        elif isinstance(node, ast.Call) and node.args:
            function = node.func
            dynamic = isinstance(function, ast.Name) and function.id in {
                "import_module",
                "__import__",
            }
            dynamic |= (
                isinstance(function, ast.Attribute) and function.attr == "import_module"
            )
            value = node.args[0]
            if (
                dynamic
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                names.add(value.value)
    return names


def within(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def check(source: Path, manifest: Path) -> list[str]:
    config = tomllib.loads(manifest.read_text())
    if config["schema_version"] != 1:
        return ["unsupported architecture schema"]
    packages = config["packages"]
    debt = config["root_debt"]
    aliases = config["compatibility"]
    errors: list[str] = []
    graph = config["plugin_dependencies"]
    for owner, dependencies in graph.items():
        if any(dependency not in graph for dependency in dependencies):
            errors.append(f"{owner}: unknown plugin dependency")
        pending = list(dependencies)
        visited: set[str] = set()
        while pending:
            sibling = pending.pop()
            if sibling == owner:
                errors.append(f"{owner}: plugin dependency graph contains a cycle")
                break
            if sibling not in visited:
                visited.add(sibling)
                pending.extend(graph.get(sibling, []))
    files = {p.relative_to(source).as_posix(): p for p in source.rglob("*.py")}
    for path in files:
        if "__pycache__" in Path(path).parts:
            continue
        directory = Path(path).parent.as_posix()
        directory = "" if directory == "." else directory
        if path in aliases:
            entry = aliases[path]
            forwarding = facade(entry["target"], entry["kind"])
            if entry.get("entrypoint") == "main":
                forwarding += (
                    '\nif __name__ == "__main__":\n    _implementation.main()\n'
                )
            expected = ast.parse(forwarding)
            if shape(ast.parse(files[path].read_text())) != shape(expected):
                errors.append(f"{path}: compatibility facade contains implementation")
            target = entry["target"].removeprefix("apizr.").replace(".", "/")
            target += "/__init__.py" if entry["kind"] == "package" else ".py"
            if target not in files or target in aliases:
                errors.append(f"{path}: compatibility target is not an implementation")
            continue
        if directory not in packages:
            errors.append(f"{path}: package has no declared responsibility")
            continue
        entry = packages[directory]
        if not entry.get("responsibility"):
            errors.append(f"{directory}: empty package responsibility")
        if entry["kind"] not in {"composition", "domain", "legacy"}:
            errors.append(f"{directory}: unknown package kind")
        if entry["kind"] == "composition" and Path(path).name not in entry["modules"]:
            if directory or path not in debt:
                errors.append(
                    f"{path}: implementation added to a composition namespace"
                )
        if entry["kind"] != "legacy" and any(
            part in GENERIC_BUCKETS for part in Path(path).parts
        ):
            errors.append(f"{path}: generic responsibility bucket")
        if entry["kind"] != "legacy" and not re.fullmatch(
            r"_?[a-z][a-z0-9_]*|__init__|__main__", Path(path).stem
        ):
            errors.append(f"{path}: module name must describe its role in snake_case")
        names = imports(ast.parse(files[path].read_text()), path)
        if entry["kind"] == "composition" and Path(path).name == "__init__.py":
            tree = ast.parse(files[path].read_text())
            for node in ast.walk(tree):
                if isinstance(
                    node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    if node.name not in entry.get("entrypoints", []):
                        errors.append(
                            f"{path}: composition initializer defines {node.name}"
                        )
        for imported in sorted(names):
            embedded = config.get("embedded_imports", {}).get(path, [])
            if any(within(imported, module_name(old)) for old in aliases) and not any(
                within(imported, allowed) for allowed in embedded
            ):
                errors.append(f"{path}: imports compatibility path {imported}")
            if not path.startswith("cli/") and within(imported, "apizr.cli"):
                errors.append(f"{path}: domain depends on CLI adapter {imported}")
            if path.startswith(("plugins/", "workspace/")) and imported.split(".")[
                0
            ] in {"fastapi", "mcp", "apizr_mcp", "apizr_oci", "apizr_attest"}:
                errors.append(
                    f"{path}: core management depends on optional adapter {imported}"
                )
            if path == "workspace/files.py" and within(imported, "apizr"):
                errors.append(
                    f"{path}: bounded file access depends on a domain {imported}"
                )
            if path.startswith("plugins/") and imported.startswith("apizr.plugins."):
                owner = path.split("/")[1]
                sibling = imported.split(".")[2]
                allowed = config["plugin_dependencies"].get(owner, [])
                if sibling != owner and sibling not in allowed:
                    errors.append(
                        f"{path}: forbidden plugin dependency {owner} -> {sibling}"
                    )
    for directory in packages:
        init = str(Path(directory) / "__init__.py")
        if init not in files:
            errors.append(
                f"{directory}: declared package is absent or lacks __init__.py"
            )
        if directory:
            parent = Path(directory).parent.as_posix()
            parent = "" if parent == "." else parent
            if parent not in packages:
                errors.append(f"{directory}: parent has no declared responsibility")
            elif packages[parent]["kind"] == "domain":
                errors.append(
                    f"{directory}: leaf domain must be declared composition before subdivision"
                )
    for path in debt:
        if path not in files or path in aliases:
            errors.append(f"{path}: stale root migration debt; remove its exception")
        if not debt[path].get("reason") or not debt[path].get("migration"):
            errors.append(f"{path}: root debt needs a reason and migration constraint")
    for path in aliases:
        if path not in files:
            errors.append(f"{path}: declared compatibility facade is absent")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "src/apizr")
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "architecture/packages.toml"
    )
    args = parser.parse_args()
    errors = check(args.source, args.manifest)
    for error in errors:
        print(error)
    if not errors:
        print(
            "PASS package composition, compatibility facades and dependency boundaries"
        )
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
