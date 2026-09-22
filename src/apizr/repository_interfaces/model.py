"""Independent repository bundle contracts, composed from shared invocations."""

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel, logical_module
from apizr.exposure.policy import Interface
from apizr.generators.mcp.model import Protocol, ToolContract
from apizr.generators.rest.model import Endpoint
from apizr.interfaces.model import InvocationContract
from apizr.repository.policy import relative_path


class BundledSource(ValueModel):
    module: str
    source_path: str
    bundle_path: str
    source_digest: Digest
    size: int = Field(ge=0)
    is_package: bool

    _module = field_validator("module")(logical_module)
    _paths = field_validator("source_path", "bundle_path")(relative_path)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        expected = (
            "source/"
            + self.module.replace(".", "/")
            + ("/__init__.py" if self.is_package else ".py")
        )
        if self.bundle_path != expected:
            raise ValueError("Source module and bundle path disagree")
        return self


class Capability(ValueModel):
    capability_id: str
    public_name: str
    module: str
    invocation: InvocationContract

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            self.capability_id != f"python:{self.module}:{self.invocation.name}"
            or self.invocation.capability_id != self.capability_id
            or self.public_name != self.module + "." + self.invocation.name
        ):
            raise ValueError("Capability identity and invocation disagree")
        return self


class RepositoryInterface(ValueModel):
    schema_version: Literal["apizr.repository-interface/v1"] = (
        "apizr.repository-interface/v1"
    )
    exposure_plan_digest: Digest
    repository_digest: Digest
    catalog_digest: Digest
    graph_digest: Digest
    repository_readiness_digest: Digest
    interface: Interface
    sources: tuple[BundledSource, ...]
    capabilities: tuple[Capability, ...]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        modules = {source.module for source in self.sources}
        if len(modules) != len(self.sources) or len(
            {s.source_path for s in self.sources}
        ) != len(self.sources):
            raise ValueError("Duplicate repository source")
        if not self.capabilities or len(
            {c.capability_id for c in self.capabilities}
        ) != len(self.capabilities):
            raise ValueError("Expected unique nonempty public capabilities")
        if any(c.module not in modules for c in self.capabilities):
            raise ValueError("Exposed capability has no bundled source")
        return self


class BundleManifest(ValueModel):
    repository_interface_digest: Digest
    exposure_plan_digest: Digest
    sources: tuple[BundledSource, ...]
    artifacts: dict[str, Digest]


class RestManifest(BundleManifest):
    schema_version: Literal["apizr.repository-rest/v1"] = "apizr.repository-rest/v1"
    endpoints: tuple[Endpoint, ...]


class MCPManifest(BundleManifest):
    schema_version: Literal["apizr.repository-mcp/v1"] = "apizr.repository-mcp/v1"
    protocol: Protocol = Protocol()
    tools: tuple[ToolContract, ...]
