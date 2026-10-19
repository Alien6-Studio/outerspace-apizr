"""Validate package composition and static dependencies without importing Apizr."""

import argparse
import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GENERIC_BUCKETS = {"utils", "helpers", "common", "services"}


def module_name(path: str) -> str:
    parts = list(Path(path).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(("apizr", *parts))


def imports(tree: ast.Module, path: str, *, members: bool = True) -> set[str]:
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
            if members:
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
    errors: list[str] = []
    if packages[""]["kind"] != "composition" or packages[""]["modules"] != [
        "__init__.py"
    ]:
        errors.append("root namespace may declare only __init__.py")
    if debt or config["compatibility"] or config.get("embedded_imports"):
        errors.append(
            "root migration, compatibility and embedded import exceptions are retired"
        )
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
    modules = {module_name(path) for path in files}
    root_domains = {name.split("/")[0] for name in packages if name}
    for path in files:
        if "__pycache__" in Path(path).parts:
            continue
        directory = Path(path).parent.as_posix()
        directory = "" if directory == "." else directory
        if directory not in packages:
            errors.append(f"{path}: package has no declared responsibility")
            continue
        entry = packages[directory]
        if not entry.get("responsibility"):
            errors.append(f"{directory}: empty package responsibility")
        if entry["kind"] not in {"composition", "domain"}:
            errors.append(f"{directory}: unknown package kind")
        if entry["kind"] == "composition" and Path(path).name not in entry["modules"]:
            errors.append(f"{path}: implementation added to a composition namespace")
        if any(part in GENERIC_BUCKETS for part in Path(path).parts):
            errors.append(f"{path}: generic responsibility bucket")
        if not re.fullmatch(r"_?[a-z][a-z0-9_]*|__init__|__main__", Path(path).stem):
            errors.append(f"{path}: module name must describe its role in snake_case")
        tree = ast.parse(files[path].read_text())
        names = imports(tree, path)
        for imported in imports(tree, path, members=False):
            if within(imported, "apizr") and imported not in modules:
                errors.append(f"{path}: imports absent core module {imported}")
        for imported in names:
            if (
                imported.startswith("apizr.")
                and imported.split(".")[1] not in root_domains
            ):
                errors.append(f"{path}: imports undeclared root domain {imported}")
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
        internal_policy = entry.get("allowed_internal_imports")
        external_policy = entry.get("allowed_external_imports")
        if internal_policy is not None and external_policy is not None:
            own_prefix = "apizr." + directory.replace("/", ".")
            for imported in sorted(names):
                if within(imported, own_prefix):
                    continue
                if imported == "apizr" or imported.startswith("apizr."):
                    if not any(within(imported, prefix) for prefix in internal_policy):
                        errors.append(
                            f"{path}: domain dependency not declared: {imported}"
                        )
                else:
                    root = imported.split(".", 1)[0]
                    if (
                        root not in sys.stdlib_module_names
                        and root not in external_policy
                    ):
                        errors.append(
                            f"{path}: external dependency not declared: {imported}"
                        )
        for imported in sorted(names):
            if path.startswith("experiments/"):
                primitives = (
                    "apizr.experiments",
                    "apizr.capabilities.types",
                    "apizr.contracts.distribution",
                    "apizr.contracts.json",
                    "apizr.contracts.json_budget",
                    "apizr.workspace.files",
                )
                # Narrow composition exceptions. Producers and Plan/Run stay primitive.
                composition_dependencies = {
                    "experiments/metrics.py": (
                        "apizr.scientific_providers.builtin.metrics",
                    ),
                    "experiments/outputs.py": (
                        "apizr.scientific_providers.builtin.outputs",
                    ),
                    "experiments/inputs.py": (
                        "apizr.scientific_providers.builtin.inputs",
                    ),
                    "experiments/randomness.py": (
                        "apizr.scientific_providers.builtin.randomness",
                    ),
                    "experiments/exposure_model.py": (
                        "apizr.capabilities.model",
                        "apizr.contracts.application",
                        "apizr.exposure",
                        "apizr.repository.serialization",
                        "apizr.repository_interfaces.model",
                    ),
                    "experiments/exposure.py": (
                        "apizr.capabilities.model",
                        "apizr.contracts.application",
                        "apizr.contracts.delivery",
                        "apizr.exposure",
                        "apizr.graph",
                        "apizr.repository",
                        "apizr.repository_readiness",
                        "apizr.repository_interfaces",
                        "apizr.workspace.application_resources",
                        "apizr.workspace.application_dependencies",
                        "apizr.workspace.compiler",
                        "apizr.workspace.operator_policy",
                        "apizr.workspace.source_access",
                        "apizr.generators.notebooks",
                    ),
                    "experiments/runner.py": (
                        "apizr.scientific_providers.contracts.model",
                        "apizr.scientific_providers.contracts.selection",
                        "apizr.execution.supervisor",
                        "apizr.execution.protocol",
                        "apizr.generators.notebooks",
                    ),
                    "experiments/worker.py": ("apizr.execution.protocol",),
                    "experiments/inspection_model.py": (
                        "apizr.scientific_providers.contracts.selection",
                        "apizr.capabilities.model",
                        "apizr.readiness",
                        "apizr.repository.model",
                        "apizr.repository_views.model",
                    ),
                    "experiments/inspection.py": (
                        "apizr.scientific_providers.contracts.model",
                        "apizr.scientific_providers.contracts.selection",
                        "apizr.scientific_providers.selection",
                        "apizr.scientific_providers.builtin.locations",
                        "apizr.scientific_providers.builtin.recognition",
                        "apizr.capabilities",
                        "apizr.readiness",
                        "apizr.repository.model",
                        "apizr.graph.model",
                        "apizr.repository_readiness",
                        "apizr.repository_views",
                        "apizr.generators.notebooks",
                    ),
                    "experiments/history.py": (
                        "apizr.scientific_providers.contracts.selection",
                    ),
                    "experiments/comparison.py": (
                        "apizr.scientific_providers.contracts.selection",
                    ),
                }
                primitives += composition_dependencies.get(path, ())
                root = imported.split(".")[0]
                if not any(
                    within(imported, allowed) for allowed in primitives
                ) and root not in (
                    sys.stdlib_module_names | {"pydantic", "typing_extensions"}
                ):
                    errors.append(
                        f"{path}: experiment contracts depend on non-primitive {imported}"
                    )
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
        print("PASS canonical package composition and dependency boundaries")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
