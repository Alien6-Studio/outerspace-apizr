"""Validate ownership, compatibility CLIs and workflow references for qualification."""

import argparse
import ast
import json
import re
import tomllib
from collections import defaultdict, deque
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
ROLES = {"smoke", "proof", "check", "prepare", "release", "fixture", "tool"}
KINDS = {"implementation", "compatibility", "namespace", "resource"}
GENERIC = {"utils", "helpers", "common", "services"}
FILE_REFERENCE = re.compile(r"\bscripts/[\w./*-]+\.(?:py|cjs|rb\.in)\b")
MODULE_REFERENCE = re.compile(r"-m\s+(scripts(?:\.[A-Za-z_]\w*)+)")


def source_files(root: Path) -> set[str]:
    result = set()
    for path in (root / "scripts").rglob("*"):
        relative = path.relative_to(root)
        if "__pycache__" in relative.parts or relative.name == ".DS_Store":
            continue
        if relative.parts[:3] == ("scripts", "client_collection_tools", "node_modules"):
            continue
        if path.is_symlink():
            raise ValueError(f"Qualification source is a symlink: {relative}")
        if path.is_file():
            result.add(relative.as_posix())
    return result


def module_name(path: str) -> str:
    name = path.removesuffix(".py").replace("/", ".")
    return name.removesuffix(".__init__")


def references(text: str, files: set[str], modules: dict[str, str]) -> set[str]:
    result = set()
    for name in FILE_REFERENCE.findall(text):
        matches = {path for path in files if Path(path).match(name)}
        if not matches:
            raise ValueError(f"Missing qualification script: {name}")
        result.update(matches)
    for name in MODULE_REFERENCE.findall(text):
        if name not in modules:
            raise ValueError(f"Missing qualification module: {name}")
        result.add(modules[name])
    return result


def facts(root: Path) -> dict[str, dict]:
    """Read direct workflow callsites and conservative static helper reachability."""
    files = source_files(root)
    modules = {module_name(path): path for path in files if path.endswith(".py")}
    direct: dict[str, set[str]] = defaultdict(set)
    retained: dict[str, set[str]] = defaultdict(set)
    edges: dict[str, set[str]] = defaultdict(set)
    for workflow_path in sorted((root / ".github/workflows").glob("*.y*ml")):
        workflow = yaml.safe_load(workflow_path.read_text())
        for job_name, job in workflow["jobs"].items():
            caller = workflow_path.name + "#" + job_name
            outputs = {"stdout/stderr (workflow step log)"}
            for step in job.get("steps", []):
                if step.get("uses", "").startswith("actions/upload-artifact@"):
                    outputs.update(step["with"]["path"].splitlines())
                text = step.get("run", "")
                for path in references(text, files, modules):
                    direct[path].add(caller)
                if "pre-commit run" in text:
                    configuration = root / ".pre-commit-config.yaml"
                    if configuration.exists():
                        hooks = yaml.safe_load(configuration.read_text())
                        for repository in hooks["repos"]:
                            if repository["repo"] == "local":
                                for hook in repository["hooks"]:
                                    for path in references(
                                        hook["entry"], files, modules
                                    ):
                                        direct[path].add(caller)
                if "--prefix scripts/client_collection_tools" in text:
                    for name in ("package.json", "package-lock.json"):
                        path = "scripts/client_collection_tools/" + name
                        if path not in files:
                            raise ValueError(f"Missing client tool resource: {path}")
                        direct[path].add(caller)
            retained[caller] = {name for name in outputs if name}
    for path in files:
        if not path.endswith(".py"):
            continue
        text = (root / path).read_text()
        tree = ast.parse(text)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names = [
                    node.module,
                    *(node.module + "." + alias.name for alias in node.names),
                ]
            elif (
                isinstance(node, ast.Call)
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                if isinstance(node.args[0].value, str):
                    names = [node.args[0].value]
            for name in names:
                if name in modules:
                    edges[path].add(modules[name])
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                # Existing scripts invoke stable CLI paths as well as imports.
                for name in FILE_REFERENCE.findall(node.value):
                    edges[path].update(p for p in files if Path(p).match(name))
                value = node.value
                if value.endswith(".py") and "/" not in value:
                    sibling = str(Path(path).parent / value)
                    if sibling in files:
                        edges[path].add(sibling)
    reachable: dict[str, set[str]] = defaultdict(set)
    for path, callers in direct.items():
        pending = deque([path])
        seen = set()
        while pending:
            current = pending.popleft()
            if current in seen:
                continue
            seen.add(current)
            reachable[current].update(callers)
            pending.extend(edges[current])
    return {
        path: {
            "workflows": sorted(direct[path]),
            "ci_blocking": bool(reachable[path]),
            "evidence": sorted(
                {item for caller in reachable[path] for item in retained[caller]}
            )
            or ["stdout/stderr (manual developer command)"],
        }
        for path in sorted(files)
    }


def facade(module: str, path: str, standalone: bool) -> str:
    """The only permitted stable-CLI forwarding shape; never copies proof logic."""
    bootstrap = (
        ""
        if standalone
        else "    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
    )
    return f"""import runpy
import sys
from importlib import import_module
from pathlib import Path
if __name__ == "__main__":
{bootstrap}    runpy.run_path(str(Path(__file__).resolve().parents[1] / {path!r}), run_name="__main__")
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    _implementation = import_module({module!r})
    sys.modules[__name__] = _implementation
    globals().update(vars(_implementation))
"""


def shape(source: str) -> str:
    tree = ast.parse(source)
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        tree.body.pop(0)
    return ast.dump(tree, include_attributes=False)


def check(root: Path) -> dict:
    manifest = tomllib.loads((root / "architecture/scripts.toml").read_text())
    if manifest["schema_version"] != 1:
        raise ValueError("Unsupported qualification inventory schema")
    entries = manifest["files"]
    actual = facts(root)
    if set(entries) != set(actual):
        raise ValueError(
            f"Qualification ownership drift: missing={sorted(set(actual) - set(entries))}, stale={sorted(set(entries) - set(actual))}"
        )
    legacy = {
        Path(path).stem
        for path, value in entries.items()
        if value["kind"] == "compatibility"
    }
    for path, entry in entries.items():
        if entry["role"] not in ROLES or entry["kind"] not in KINDS:
            raise ValueError(f"Unknown qualification role/kind: {path}")
        owner = manifest["groups"].get(entry["group"])
        if owner is None or not owner.get("responsibility") or not entry.get("gate"):
            raise ValueError(f"Missing qualification responsibility: {path}")
        if GENERIC & set(Path(path).parts):
            raise ValueError(f"Generic qualification bucket: {path}")
        for name in ("workflows", "ci_blocking", "evidence"):
            if entry[name] != actual[path][name]:
                raise ValueError(f"Stale {name} inventory: {path}")
        if entry["kind"] == "compatibility":
            target = entry["canonical"]
            if target not in entries or entries[target]["kind"] != "implementation":
                raise ValueError(f"Missing single qualification implementation: {path}")
            if entries[target]["group"] != entry["group"]:
                raise ValueError(f"Qualification facade changes owner: {path}")
            if entries[target].get("source_free") and not entry["standalone"]:
                raise ValueError(f"Source-free CLI adds the checkout: {path}")
            expected = facade(module_name(target), target, entry["standalone"])
            if shape((root / path).read_text()) != shape(expected):
                raise ValueError(
                    f"Qualification facade contains implementation: {path}"
                )
        elif entry["kind"] == "implementation":
            if (
                owner["kind"] != "domain"
                or Path(path).parent.as_posix() + "/" != owner["prefix"]
                or len(Path(path).parts) == 2
            ):
                raise ValueError(f"Misplaced qualification implementation: {path}")
            tree = ast.parse((root / path).read_text())
            for node in ast.walk(tree):
                imports = (
                    [alias.name.split(".")[0] for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module.split(".")[0]]
                    if isinstance(node, ast.ImportFrom) and node.module
                    else []
                )
                if legacy & set(imports) or "mcp_distribution" in imports:
                    raise ValueError(
                        f"Qualification implementation imports compatibility CLI: {path}"
                    )
                if entry.get("source_free") and any(
                    name == "scripts" for name in imports
                ):
                    raise ValueError(
                        f"Source-free proof imports checkout helpers: {path}"
                    )
        elif entry["kind"] == "namespace":
            allowed = owner.get("namespaces", [owner["prefix"] + "__init__.py"])
            if path not in allowed:
                raise ValueError(f"Undeclared qualification composition: {path}")
            if shape((root / path).read_text()) != shape(""):
                raise ValueError(
                    f"Qualification composition namespace contains operations: {path}"
                )
    return {
        "result": "pass",
        "files": len(entries),
        "groups": len(manifest["groups"]),
        "compatibility_clis": sum(
            e["kind"] == "compatibility" for e in entries.values()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = check(ROOT)
    value = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(value)
    print(value, end="")


if __name__ == "__main__":
    main()
