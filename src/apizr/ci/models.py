"""Portable retained CI evidence; never a forge or authorization contract."""

from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel
from apizr.repository.policy import relative_path

Operation = Literal["check", "build-rest", "build-mcp"]
MAX_ARTIFACTS = 4096
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024


class Artifact(ValueModel):
    path: str = Field(max_length=512)
    digest: Digest
    size: int = Field(ge=0, le=MAX_ARTIFACT_BYTES)

    _path = field_validator("path")(relative_path)


class CIResult(ValueModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    schema_version: Literal["apizr.ci-result/v1"] = "apizr.ci-result/v1"
    operation: Operation
    state: Literal["success", "refused", "invalid"]
    diagnostic: Literal[
        "ci_complete",
        "ci_doctor_failed",
        "ci_readiness_refused",
        "ci_exposure_refused",
        "ci_bundle_refused",
    ]
    project_digest: Digest
    repository_digest: Digest | None = None
    readiness_digest: Digest | None = None
    readiness_exit_code: Literal[0, 1] | None = None
    exposure_plan_digest: Digest | None = None
    bundle_interface: Literal["rest", "mcp"] | None = None
    bundle_manifest_digest: Digest | None = None
    artifacts: tuple[Artifact, ...] = Field(max_length=MAX_ARTIFACTS)

    @model_validator(mode="after")
    def consistent(self) -> Self:
        paths = [a.path for a in self.artifacts]
        if paths != sorted(set(paths)) or "result.json" in paths:
            raise ValueError(
                "Artifact identities must be unique, sorted and nonrecursive"
            )
        if sum(a.size for a in self.artifacts) > MAX_TOTAL_BYTES:
            raise ValueError("CI artifacts exceed size limit")
        if (self.readiness_digest is None) != (self.readiness_exit_code is None):
            raise ValueError("Readiness identity requires its exit status")
        if (self.bundle_interface is None) != (self.bundle_manifest_digest is None):
            raise ValueError("Bundle identity requires its interface")
        if self.bundle_interface and self.operation != "build-" + self.bundle_interface:
            raise ValueError("Bundle interface must match the operation")
        if self.state == "success" and (
            self.diagnostic != "ci_complete"
            or self.readiness_exit_code != 0
            or self.exposure_plan_digest is None
            or (self.operation != "check" and self.bundle_interface is None)
        ):
            raise ValueError("Success requires complete evidence for the operation")
        return self

    @property
    def exit_code(self) -> int:
        return {"success": 0, "refused": 1, "invalid": 2}[self.state]
