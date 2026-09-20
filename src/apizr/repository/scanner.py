"""Orchestrate existing Inspection; never reinterpret capability semantics."""

from collections.abc import Iterable
from pathlib import Path, PurePosixPath

from apizr.capabilities.model import Digest
from apizr.inspection import inspect_source, json_bytes

from .discovery import Budget, ScanError, ScanLimit, SourceInput, discover
from .model import (
    Catalog,
    Code,
    Diagnostic,
    SourceUnit,
    capability_entries,
    repository_digest,
)
from .modules import module_name, source_root
from .policy import ScanPolicy, relative_path
from .serialization import policy_digest


def assemble(
    sources: Iterable[SourceInput],
    policy: ScanPolicy,
    diagnostics: Iterable[Diagnostic] = (),
) -> Catalog:
    """Analyze a bounded discovered manifest; filesystem I/O belongs to discovery."""
    units: list[SourceUnit] = []
    messages = list(diagnostics)
    contents: dict[str, bytes] = {}
    for source in sorted(sources, key=lambda s: s.path):
        root = source_root(source.path, policy)
        if root is None:
            raise ScanError("Manifest contains an unselected source")
        try:
            module = module_name(source.path, root)
        except ValueError:
            module = None
            messages.append(Diagnostic(code=Code.MODULE, path=source.path))
        units.append(
            SourceUnit(
                path=source.path,
                source_root=root,
                module=module,
                source_digest=Digest.of_bytes(source.content)
                if source.content is not None
                else None,
                size=source.size,
                is_package=PurePosixPath(source.path).name == "__init__.py",
            )
        )
        if source.content is not None:
            contents[source.path] = source.content
    modules: dict[str, list[SourceUnit]] = {}
    for unit in units:
        if unit.module is not None:
            modules.setdefault(unit.module, []).append(unit)
    analyzed: list[SourceUnit] = []
    for unit in units:
        if unit.module is not None and len(modules[unit.module]) > 1:
            messages.append(Diagnostic(code=Code.COLLISION, path=unit.path))
        elif unit.module is not None and unit.path in contents:
            try:
                inspection = inspect_source(
                    contents[unit.path], module_name=unit.module
                )
                unit = unit.model_copy(
                    update={
                        "inspection": inspection,
                        "inspection_digest": Digest.of_bytes(json_bytes(inspection)),
                    }
                )
            except (UnicodeError, LookupError):
                messages.append(Diagnostic(code=Code.ENCODING, path=unit.path))
            except SyntaxError as error:
                messages.append(
                    Diagnostic(
                        code=Code.PARSE,
                        path=unit.path,
                        line=error.lineno
                        if error.lineno and error.lineno > 0
                        else None,
                    )
                )
            except ValueError:
                messages.append(Diagnostic(code=Code.PARSE, path=unit.path))
            except RecursionError:
                messages.append(Diagnostic(code=Code.ANALYSIS, path=unit.path))
        analyzed.append(unit)
    ordered = tuple(
        sorted(
            set(messages),
            key=lambda d: (d.path, d.line or 0, d.code.value, d.limit or ""),
        )
    )
    result = tuple(analyzed)
    return Catalog(
        scan_policy=policy,
        scan_policy_digest=policy_digest(policy),
        repository_digest=repository_digest(policy, result, ordered),
        sources=result,
        capabilities=capability_entries(result),
        diagnostics=ordered,
    )


def scan(root: str | Path, *, policy: ScanPolicy | None = None) -> Catalog:
    selected = (
        ScanPolicy()
        if policy is None
        else ScanPolicy.model_validate(policy.model_dump(mode="json"))
    )
    sources, diagnostics = discover(root, selected)
    return assemble(sources, selected, diagnostics)


def scan_sources(
    sources: Iterable[tuple[str, bytes]], *, policy: ScanPolicy | None = None
) -> Catalog:
    """Scan an in-memory (relative path, exact bytes) manifest without a VFS.

    Caller owns input bytes. Entries must be unique. Global limit failures discard
    the inventory; excluded paths consume only the enumeration budget.
    """
    selected = (
        ScanPolicy()
        if policy is None
        else ScanPolicy.model_validate(policy.model_dump(mode="json"))
    )
    budget = Budget(selected)
    found: list[SourceInput] = []
    diagnostics: list[Diagnostic] = []
    seen: set[str] = set()
    try:
        for path, content in sources:
            budget.entry()
            path = relative_path(path)
            if source_root(path, selected) is None:
                continue
            if path in seen:
                raise ScanError("Manifest contains duplicate paths")
            seen.add(path)
            budget.source()
            if len(content) > selected.max_file_bytes:
                found.append(SourceInput(path, None, len(content)))
                diagnostics.append(Diagnostic(code=Code.SIZE, path=path))
            else:
                budget.content(len(content))
                found.append(SourceInput(path, content, len(content)))
    except ScanLimit as error:
        return assemble((), selected, (error.diagnostic,))
    return assemble(found, selected, diagnostics)
