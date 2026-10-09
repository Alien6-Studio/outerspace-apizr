"""Portable local-DX outcomes; operational paths never enter reports."""

from typing import Literal

from pydantic import Field

from apizr.contracts.publication import Model

Profile = Literal["core", "mcp", "oci", "delivery", "clients"]


class InitError(ValueError):
    """Fixed diagnostic only."""


class InitResult(Model):
    schema_version: Literal["apizr.init-result/v1"] = "apizr.init-result/v1"
    state: Literal["created"] = "created"
    files: tuple[str, ...]
    project_schema: Literal["apizr.project/v1"] = "apizr.project/v1"


class DoctorCheck(Model):
    code: str = Field(pattern=r"^[a-z0-9_]+$", max_length=80)
    status: Literal["pass", "warn", "fail", "skip"]
    summary: str = Field(max_length=256)
    action: str = Field(default="", max_length=256)


class DoctorResult(Model):
    schema_version: Literal["apizr.doctor/v1"] = "apizr.doctor/v1"
    checks: tuple[DoctorCheck, ...] = Field(max_length=128)

    @property
    def exit_code(self) -> int:
        return int(any(check.status == "fail" for check in self.checks))
