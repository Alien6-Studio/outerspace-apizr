"""Static evidence, not execution claims. Catalog remains authoritative metadata."""

from enum import Enum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from apizr.capabilities.model import Digest, ExecutionForm, Severity
from apizr.capabilities.types import Evidence, ValueModel, logical_module
from apizr.readiness import State
from apizr.repository.policy import relative_path

from .policy import GraphPolicy
from .serialization import policy_digest


class Code(str, Enum):
    INPUT = "APIZR-GRAPH-001"
    IMPORT = "APIZR-GRAPH-002"
    RELATIVE = "APIZR-GRAPH-003"
    STAR = "APIZR-GRAPH-004"
    DYNAMIC = "APIZR-GRAPH-005"
    REBOUND = "APIZR-GRAPH-006"
    CALL = "APIZR-GRAPH-007"
    LIMIT = "APIZR-GRAPH-008"
    COLLISION = "APIZR-GRAPH-009"
    UNAVAILABLE = "APIZR-GRAPH-010"


MESSAGES = {
    Code.INPUT: "Source manifest does not match the validated catalog.",
    Code.IMPORT: "Repository import has multiple or unstable interpretations.",
    Code.RELATIVE: "Relative import exceeds the logical package ancestry.",
    Code.STAR: "Star import bindings are not expanded.",
    Code.DYNAMIC: "Dynamic import target is unresolved; arguments are not evaluated.",
    Code.REBOUND: "Import binding is conditional, rebound or ambiguous.",
    Code.CALL: "Possible capability call has no stable unique target binding.",
    Code.LIMIT: "Graph resource limit exceeded; all syntax relationships discarded.",
    Code.COLLISION: "Colliding catalog modules cannot identify a unique graph node.",
    Code.UNAVAILABLE: "Catalog inspection unavailable; relationship analysis skipped.",
}


class Diagnostic(ValueModel):
    code: Code
    path: str
    line: int | None = Field(default=None, ge=1)
    column: int | None = Field(default=None, ge=0)
    limit: (
        Literal["ast_nodes", "relationships", "calls", "imports", "parser"] | None
    ) = None

    @field_validator("path")
    @classmethod
    def checked_path(cls, value: str) -> str:
        return relative_path(value, allow_root=True)

    @property
    def severity(self) -> Severity:
        return (
            Severity.ERROR
            if self.code
            in {
                Code.INPUT,
                Code.IMPORT,
                Code.RELATIVE,
                Code.LIMIT,
                Code.COLLISION,
                Code.UNAVAILABLE,
            }
            else Severity.WARNING
        )

    @property
    def message(self) -> str:
        return MESSAGES[self.code]


def module_id(module: str) -> str:
    return f"python-module:{logical_module(module)}"


def external_id(module: str) -> str:
    return f"python-external:{logical_module(module)}"


class ModuleNode(ValueModel):
    kind: Literal["module"] = "module"
    id: str
    module: str
    path: str
    analyzed: bool

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.id != module_id(self.module) or self.path != relative_path(self.path):
            raise ValueError("Module node identity/path mismatch")
        return self


class CapabilityNode(ValueModel):
    kind: Literal["capability"] = "capability"
    id: str
    module: str
    name: str
    path: str
    readiness: State
    can_generate_interface: bool
    execution: ExecutionForm

    @model_validator(mode="after")
    def identity(self) -> Self:
        logical_module(self.module)
        if (
            "." in logical_module(self.name)
            or self.id != f"python:{self.module}:{self.name}"
        ):
            raise ValueError("Capability identity mismatch")
        if self.path != relative_path(self.path):
            raise ValueError("Invalid capability path")
        if self.can_generate_interface != (self.readiness == State.READY):
            raise ValueError("Capability eligibility disagrees with readiness")
        return self


class ExternalNode(ValueModel):
    kind: Literal["external_module"] = "external_module"
    id: str
    module: str

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.id != external_id(self.module):
            raise ValueError("External module identity mismatch")
        return self


Node = Annotated[
    ModuleNode | CapabilityNode | ExternalNode, Field(discriminator="kind")
]
Availability = Literal["unconditional", "conditional"]
Scope = Literal["module_scope", "capability_scope"]


class Location(ValueModel):
    path: str
    line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    column: int = Field(ge=0)
    end_column: int = Field(ge=0)
    availability: Availability

    @model_validator(mode="after")
    def valid_span(self) -> Self:
        if self.path != relative_path(self.path):
            raise ValueError("Noncanonical evidence path")
        if (self.end_line, self.end_column) < (self.line, self.column):
            raise ValueError("Reversed evidence span")
        return self


class RelationshipKind(str, Enum):
    CONTAINS = "contains"
    MODULE = "imports_module"
    EXTERNAL = "imports_external_module"
    CAPABILITY = "imports_capability"
    CALL = "calls_capability"


class Relationship(Location):
    source: str
    target: str
    kind: RelationshipKind
    syntax_evidence: Literal[Evidence.OBSERVED] = Evidence.OBSERVED
    resolution_evidence: Literal[Evidence.OBSERVED, Evidence.INFERRED]


class ImportedName(ValueModel):
    name: str
    alias: str | None = None
    resolution: Literal[
        "module", "capability", "external", "unresolved", "ambiguous", "star"
    ]
    target: str | None = None
    resolution_evidence: Literal[Evidence.INFERRED, Evidence.UNKNOWN] = Evidence.UNKNOWN

    @model_validator(mode="after")
    def consistent(self) -> Self:
        resolved = self.resolution in {"module", "capability", "external"}
        if resolved != (self.target is not None):
            raise ValueError("Import resolution must agree with target presence")
        expected = Evidence.INFERRED if resolved else Evidence.UNKNOWN
        if self.resolution_evidence != expected:
            raise ValueError("Import resolution evidence mismatch")
        if self.name != "*":
            logical_module(self.name)
        if self.alias is not None and "." in logical_module(self.alias):
            raise ValueError("Import alias must be one identifier")
        return self


class ImportDeclaration(Location):
    source: str
    scope: Scope
    syntax: Literal["import", "from"]
    declared_module: str | None
    relative_level: int = Field(ge=0)
    names: tuple[ImportedName, ...]
    evidence: Literal[Evidence.OBSERVED] = Evidence.OBSERVED


def relationship_key(r: Relationship) -> tuple[str, str, str, str, int, int, int, int]:
    return (
        r.source,
        r.kind.value,
        r.target,
        r.path,
        r.line,
        r.column,
        r.end_line,
        r.end_column,
    )


def diagnostic_key(d: Diagnostic) -> tuple[str, int, int, str, str]:
    return (d.path, d.line or 0, d.column or 0, d.code.value, d.limit or "")


class Statistics(ValueModel):
    modules: int
    capabilities: int
    external_modules: int
    relationships: dict[RelationshipKind, int]
    import_declarations: int
    diagnostics: int


class Graph(ValueModel):
    schema_version: Literal["apizr.graph/v1"] = "apizr.graph/v1"
    catalog_digest: Digest
    repository_digest: Digest
    graph_policy: GraphPolicy
    graph_policy_digest: Digest
    catalog_exit_code: Literal[0, 1]
    complete: bool
    nodes: tuple[Node, ...]
    relationships: tuple[Relationship, ...]
    imports: tuple[ImportDeclaration, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()

    @field_validator("nodes")
    @classmethod
    def ordered_nodes(cls, nodes: tuple[Node, ...]) -> tuple[Node, ...]:
        if len({n.id for n in nodes}) != len(nodes):
            raise ValueError("Duplicate graph node identity")
        return tuple(sorted(nodes, key=lambda n: n.id))

    @field_validator("relationships")
    @classmethod
    def ordered_edges(
        cls, values: tuple[Relationship, ...]
    ) -> tuple[Relationship, ...]:
        return tuple(sorted(set(values), key=relationship_key))

    @field_validator("imports")
    @classmethod
    def ordered_imports(
        cls, values: tuple[ImportDeclaration, ...]
    ) -> tuple[ImportDeclaration, ...]:
        return tuple(
            sorted(set(values), key=lambda d: (d.source, d.path, d.line, d.column))
        )

    @field_validator("diagnostics")
    @classmethod
    def ordered_diagnostics(
        cls, values: tuple[Diagnostic, ...]
    ) -> tuple[Diagnostic, ...]:
        return tuple(sorted(set(values), key=diagnostic_key))

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.graph_policy_digest != policy_digest(self.graph_policy):
            raise ValueError("Graph policy digest mismatch")
        nodes = {n.id: n for n in self.nodes}
        kinds = {
            RelationshipKind.CONTAINS: ({"module"}, "capability"),
            RelationshipKind.MODULE: ({"module", "capability"}, "module"),
            RelationshipKind.EXTERNAL: ({"module", "capability"}, "external_module"),
            RelationshipKind.CAPABILITY: ({"module", "capability"}, "capability"),
            RelationshipKind.CALL: ({"capability"}, "capability"),
        }
        for edge in self.relationships:
            source, target = nodes.get(edge.source), nodes.get(edge.target)
            allowed, target_kind = kinds[edge.kind]
            if (
                source is None
                or target is None
                or source.kind not in allowed
                or target.kind != target_kind
            ):
                raise ValueError("Relationship endpoints/kind mismatch")
            if isinstance(source, ExternalNode) or source.path != edge.path:
                raise ValueError("Relationship evidence outside source module")
            expected = (
                Evidence.OBSERVED
                if edge.kind == RelationshipKind.CONTAINS
                else Evidence.INFERRED
            )
            if edge.resolution_evidence != expected:
                raise ValueError("Relationship resolution evidence mismatch")
            if (
                edge.kind == RelationshipKind.CONTAINS
                and source.module != target.module
            ):
                raise ValueError("Containment module mismatch")
        for declaration in self.imports:
            source = nodes.get(declaration.source)
            if (
                source is None
                or isinstance(source, ExternalNode)
                or source.path != declaration.path
            ):
                raise ValueError("Import source mismatch")
            if declaration.scope != (
                "module_scope" if source.kind == "module" else "capability_scope"
            ):
                raise ValueError("Import lexical scope mismatch")
            for name in declaration.names:
                if name.target is not None:
                    target = nodes.get(name.target)
                    expected_kind = {
                        "module": "module",
                        "capability": "capability",
                        "external": "external_module",
                    }[name.resolution]
                    if target is None or target.kind != expected_kind:
                        raise ValueError(
                            "Import target missing or inconsistent with resolution"
                        )
        if self.complete and (
            self.catalog_exit_code
            or any(d.severity == Severity.ERROR for d in self.diagnostics)
        ):
            raise ValueError("Blocking diagnostics cannot describe a complete graph")
        if any(d.code == Code.LIMIT for d in self.diagnostics) and (
            self.relationships or self.imports
        ):
            raise ValueError(
                "Resource failure cannot retain a partial relationship prefix"
            )
        if (
            len(self.relationships) > self.graph_policy.max_relationships
            or len(self.imports) > self.graph_policy.max_imports
        ):
            raise ValueError("Graph exceeds its declared limits")
        return self

    @property
    def exit_code(self) -> int:
        return int(not self.complete)

    @property
    def statistics(self) -> Statistics:
        return Statistics(
            modules=sum(n.kind == "module" for n in self.nodes),
            capabilities=sum(n.kind == "capability" for n in self.nodes),
            external_modules=sum(n.kind == "external_module" for n in self.nodes),
            relationships={
                kind: sum(r.kind == kind for r in self.relationships)
                for kind in RelationshipKind
            },
            import_declarations=len(self.imports),
            diagnostics=len(self.diagnostics),
        )

    def module_dependencies(self, module: str) -> tuple[str, ...]:
        """Direct local/external module imports at module scope (node IDs)."""
        return tuple(
            sorted(
                {
                    r.target
                    for r in self.relationships
                    if r.source == module_id(module)
                    and r.kind in {RelationshipKind.MODULE, RelationshipKind.EXTERNAL}
                }
            )
        )

    def capability_calls(self, capability_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    r.target
                    for r in self.relationships
                    if r.source == capability_id and r.kind == RelationshipKind.CALL
                }
            )
        )

    def callers_of(self, capability_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    r.source
                    for r in self.relationships
                    if r.target == capability_id and r.kind == RelationshipKind.CALL
                }
            )
        )
