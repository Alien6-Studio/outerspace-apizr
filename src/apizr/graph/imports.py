"""Lexical imports, distinct from symbol use or invocation."""

import ast
from dataclasses import dataclass
from typing import Literal

from apizr.capabilities.types import Evidence

from .analysis import Analysis, location
from .bindings import Inventory, Site
from .model import (
    Code,
    ImportDeclaration,
    ImportedName,
    RelationshipKind,
    Scope,
    module_id,
)


@dataclass(frozen=True)
class Binding:
    prefix: str
    target: str
    kind: Literal["module", "capability", "external", "dynamic"]
    statement: ast.Import | ast.ImportFrom
    conditional: bool


def relative_module(
    module: str, is_package: bool, declared: str | None, level: int
) -> str | None:
    if not level:
        return declared
    package = module.split(".") if is_package else module.split(".")[:-1]
    if level > len(package):
        return None
    base = package[: len(package) - level + 1]
    return ".".join([*base, *([declared] if declared else [])])


def declarations(
    analysis: Analysis,
    sites: tuple[Site, ...],
    *,
    module: str,
    path: str,
    is_package: bool,
    source: str,
    scope: Scope,
) -> tuple[Binding, ...]:
    result: list[Binding] = []
    for site in sites:
        node = site.node
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        names: list[ImportedName] = []
        base = (
            relative_module(module, is_package, node.module, node.level)
            if isinstance(node, ast.ImportFrom)
            else None
        )
        if isinstance(node, ast.ImportFrom) and base is None:
            analysis.diagnostic(Code.RELATIVE, path, site)
        for alias in node.names:
            bound_name = alias.asname or (
                alias.name.split(".")[0] if isinstance(node, ast.Import) else alias.name
            )
            target: str | None = None
            kind: Literal[
                "module", "capability", "external", "unresolved", "ambiguous", "star"
            ] = "unresolved"
            declared = alias.name if isinstance(node, ast.Import) else base
            if declared is not None:
                if declared in analysis.index.collisions:
                    kind = "ambiguous"
                    analysis.diagnostic(Code.IMPORT, path, site)
                elif isinstance(node, ast.Import):
                    if declared in analysis.index.modules:
                        kind, target = "module", module_id(declared)
                    else:
                        kind, target = "external", analysis.external(declared)
                else:
                    # The base-module import remains a distinct fact, even for
                    # unresolved non-capability symbols and star imports.
                    base_local = declared in analysis.index.modules
                    if base_local:
                        analysis.edge(
                            source,
                            module_id(declared),
                            RelationshipKind.MODULE,
                            location(path, site),
                        )
                    candidate = declared + "." + alias.name
                    capability = analysis.index.capabilities.get((declared, alias.name))
                    submodule = candidate in analysis.index.modules
                    symbol = (
                        competing_symbol(analysis, declared, alias.name, candidate)
                        or capability is not None
                    )
                    if alias.name == "*":
                        kind = "star"
                        if not base_local:
                            analysis.edge(
                                source,
                                analysis.external(declared),
                                RelationshipKind.EXTERNAL,
                                location(path, site),
                            )
                    elif (
                        candidate in analysis.index.collisions
                        or (submodule and symbol)
                        or (
                            capability is not None
                            and capability.id not in analysis.index.stable
                        )
                    ):
                        kind = "ambiguous"
                        analysis.diagnostic(Code.IMPORT, path, site)
                    elif submodule:
                        kind, target = "module", module_id(candidate)
                    elif capability is not None:
                        kind, target = "capability", capability.id
                    elif not base_local:
                        kind, target = "external", analysis.external(declared)
            if alias.name == "*":
                analysis.diagnostic(Code.STAR, path, site)
            if target is not None:
                edge_kind = {
                    "module": RelationshipKind.MODULE,
                    "capability": RelationshipKind.CAPABILITY,
                    "external": RelationshipKind.EXTERNAL,
                }[kind]
                analysis.edge(source, target, edge_kind, location(path, site))
            names.append(
                ImportedName(
                    name=alias.name,
                    alias=alias.asname,
                    resolution=kind,
                    target=target,
                    resolution_evidence=Evidence.INFERRED
                    if target is not None
                    else Evidence.UNKNOWN,
                )
            )
            prefix = (
                alias.name
                if isinstance(node, ast.Import) and alias.asname is None
                else bound_name
            )
            binding_kind: (
                Literal["module", "capability", "external", "dynamic"] | None
            ) = None
            binding_target = target
            if kind in {"module", "capability", "external"} and target is not None:
                if kind == "module":
                    binding_kind = "module"
                    binding_target = target.removeprefix("python-module:")
                elif kind == "capability":
                    binding_kind = "capability"
                else:
                    binding_kind = "external"
            if (
                isinstance(node, ast.ImportFrom)
                and node.level == 0
                and node.module == "importlib"
                and kind == "external"
                and alias.name == "import_module"
                and "importlib" not in analysis.index.modules
                and "importlib" not in analysis.index.collisions
            ):
                binding_kind, binding_target = "dynamic", "importlib.import_module"
            elif (
                isinstance(node, ast.Import)
                and alias.name == "importlib"
                and kind == "external"
            ):
                binding_kind, binding_target = "dynamic", "importlib"
            if binding_kind is not None and binding_target is not None:
                result.append(
                    Binding(
                        prefix,
                        binding_target,
                        binding_kind,
                        node,
                        site.availability == "conditional",
                    )
                )
        analysis.imports.append(
            ImportDeclaration(
                **location(path, site).model_dump(),
                source=source,
                scope=scope,
                syntax="import" if isinstance(node, ast.Import) else "from",
                declared_module=None if isinstance(node, ast.Import) else node.module,
                relative_level=0 if isinstance(node, ast.Import) else node.level,
                names=tuple(names),
            )
        )
    return tuple(result)


def stable_bindings(
    bindings: tuple[Binding, ...], inventory: Inventory, analysis: Analysis, path: str
) -> tuple[Binding, ...]:
    result: list[Binding] = []
    groups: dict[str, list[Binding]] = {}
    dotted: dict[tuple[ast.AST, str], bool] = {}
    statements = {binding.statement for binding in bindings}
    for statement in statements:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                root = alias.asname or alias.name.split(".")[0]
                key = (statement, root)
                dotted[key] = (
                    dotted.get(key, True)
                    and alias.asname is None
                    and alias.name.startswith(root + ".")
                )
    for binding in bindings:
        groups.setdefault(binding.prefix.split(".")[0], []).append(binding)
    for root, peers in groups.items():
        writes = inventory.writes.get(root, [])
        dotted_group = all(dotted.get((write, root), False) for write in writes)
        conflicting = len({b.prefix for b in peers}) != len(
            {(b.prefix, b.target, b.kind) for b in peers}
        )
        safe = (
            not conflicting
            and (len(writes) == 1 or dotted_group)
            and not any(b.conditional for b in peers)
            and not inventory.star
        )
        for binding in peers:
            if safe:
                result.append(binding)
            else:
                analysis.diagnostic(
                    Code.REBOUND,
                    path,
                    Site(
                        binding.statement,
                        "conditional" if binding.conditional else "unconditional",
                    ),
                )
    return tuple(result)


def competing_symbol(
    analysis: Analysis, module: str, name: str, candidate: str
) -> bool:
    """A direct import of the same submodule is not a competing export.

    Everything else bound under that name is unresolved export evidence. This
    narrow check does not chase re-export chains or assignment aliases.
    """
    return any(
        target != candidate
        for target in analysis.index.symbols.get(module, {}).get(name, set())
    )


def symbol_inventory(
    inventory: Inventory, module: str, is_package: bool
) -> dict[str, set[str | None]]:
    """Preindex declarations once; do not rescan wide alias lists per symbol."""
    imported: dict[tuple[ast.AST, str], set[str | None]] = {}
    statements = {write for writes in inventory.writes.values() for write in writes}
    for statement in statements:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                name = alias.asname or alias.name.split(".")[0]
                target = alias.name if alias.asname else alias.name.split(".")[0]
                imported.setdefault((statement, name), set()).add(target)
        elif isinstance(statement, ast.ImportFrom):
            base = relative_module(
                module, is_package, statement.module, statement.level
            )
            for alias in statement.names:
                name = alias.asname or alias.name
                imported.setdefault((statement, name), set()).add(
                    base + "." + alias.name if base is not None else None
                )
    return {
        name: {
            target for write in writes for target in imported.get((write, name), {None})
        }
        for name, writes in inventory.writes.items()
    }


def binding_map(bindings: tuple[Binding, ...]) -> dict[str, Binding]:
    result: dict[str, Binding] = {}
    for binding in bindings:
        result.setdefault(binding.prefix, binding)
    return result
