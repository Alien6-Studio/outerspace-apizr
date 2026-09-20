"""Resolve direct ast.Call targets only, never arbitrary attribute/object values."""

import ast
from collections.abc import Mapping

from .analysis import Analysis, location
from .bindings import Inventory, Site, dotted
from .imports import Binding
from .model import Code, RelationshipKind


def analyze_calls(
    analysis: Analysis,
    sites: tuple[Site, ...],
    *,
    module: str,
    path: str,
    caller: str | None,
    local: Inventory,
    module_inventory: Inventory,
    local_imports: Mapping[str, Binding],
    module_imports: Mapping[str, Binding],
) -> None:
    for site in sites:
        node = site.node
        if not isinstance(node, ast.Call):
            continue
        expression = dotted(node.func)
        if expression is None:
            continue
        root = expression.split(".")[0]
        if root in site.shadows or root in local.nonlocals:
            continue
        local_name = root in local.writes and root not in local.globals
        if root in local.globals and root in local.writes:
            continue
        bindings = local_imports if local_name else module_imports
        blocked = local.star or (not local_name and module_inventory.star)
        if blocked:
            continue
        if (
            expression == "__import__"
            and not local_name
            and root not in module_inventory.writes
        ):
            analysis.diagnostic(Code.DYNAMIC, path, site)
            continue
        prefix = expression
        binding = bindings.get(prefix)
        while binding is None and "." in prefix:
            prefix = prefix.rsplit(".", 1)[0]
            binding = bindings.get(prefix)
        target: str | None = None
        uncertain = False
        if binding is not None:
            # Local imports execute in the body: no claim for use before binding.
            if local_name and (node.lineno, node.col_offset) <= (
                binding.statement.lineno,
                binding.statement.col_offset,
            ):
                analysis.diagnostic(Code.CALL, path, site)
                continue
            suffix = expression[len(binding.prefix) :].lstrip(".")
            if binding.kind == "dynamic":
                if (binding.target == "importlib" and suffix == "import_module") or (
                    binding.target == "importlib.import_module" and not suffix
                ):
                    analysis.diagnostic(Code.DYNAMIC, path, site)
            elif binding.kind == "capability" and not suffix:
                target = binding.target
            elif binding.kind == "module" and suffix and "." not in suffix:
                capability = analysis.index.capabilities.get((binding.target, suffix))
                if capability is not None:
                    if capability.id in analysis.index.stable:
                        target = capability.id
                    else:
                        uncertain = True
        elif not local_name and "." not in expression:
            capability = analysis.index.capabilities.get((module, expression))
            if capability is not None:
                writes = module_inventory.writes.get(expression, [])
                if (
                    capability.id in analysis.index.stable
                    and len(writes) == 1
                    and isinstance(writes[0], (ast.FunctionDef, ast.AsyncFunctionDef))
                ):
                    target = capability.id
                else:
                    uncertain = True
        if caller is not None:
            if target is not None:
                analysis.edge(
                    caller, target, RelationshipKind.CALL, location(path, site)
                )
            elif uncertain:
                analysis.diagnostic(Code.CALL, path, site)
