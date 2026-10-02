"""Explicit local metadata checks; no repair, discovery, lock or invocation."""

import json
import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel

from apizr.config_files import absolute_path, directory_fd, read_regular
from apizr.exposure.policy import ExposurePolicy
from apizr.extension_runtime import PrerequisiteMissing
from apizr.extension_runtime.protocol import unique_object
from apizr.local_plugins import activation, store
from apizr.local_plugins.models import Installation, PluginError
from apizr.operator_policy import MAX_POLICY_BYTES, AuthorizationDenied, OperatorPolicy
from apizr.optional import available
from apizr.project import load_project
from apizr.repository_readiness.policy import RepositoryReadinessPolicy
from apizr.runtime import validate_python_target
from apizr.source_access import open_analysis_root

from .models import DoctorCheck, DoctorResult, Profile

PROFILES = ("core", "mcp", "oci", "delivery", "clients")
MODULES = {
    "mcp": "apizr_mcp",
    "oci": "apizr_oci.protocol",
    "attest": "apizr_attest.protocol",
}
T = TypeVar("T", bound=BaseModel)


def load_json(path: Path, model: type[T], limit: int = MAX_POLICY_BYTES) -> T:
    raw = read_regular(path, limit)
    json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    return model.model_validate_json(raw, strict=True)


class Checks:
    def __init__(self) -> None:
        self.items: list[DoctorCheck] = []

    def add(
        self,
        code: str,
        status: Literal["pass", "warn", "fail", "skip"],
        summary: str,
        action: str = "",
    ) -> None:
        self.items.append(
            DoctorCheck(code=code, status=status, summary=summary, action=action)
        )


def active_plugins(
    directory: Path | None, core: str, requested: tuple[str, ...], checks: Checks
) -> dict[str, Installation]:
    records: dict[str, Installation] = {}
    try:
        if directory is None:
            raise PluginError("explicit_store_required")
        with directory_fd(directory):
            pass
        root = store.storage_directory(directory)
        with directory_fd(root):
            store.validate_directory(root)
            inventory = store.read_inventory(root)
            state = activation.validated_activations(root, inventory)
            for kind in requested:
                record = next(
                    (
                        r
                        for r in state.activations
                        if r.name == f"outerspace-apizr-{kind}"
                    ),
                    None,
                )
                if record is None:
                    checks.add(
                        f"{kind}_plugin_active",
                        "fail",
                        "Official plugin is absent or inactive.",
                        "Install the official plugin explicitly, then use apizr plugins enable NAME --version VERSION.",
                    )
                    continue
                try:
                    activation._interpreter(record, root)
                    if (
                        record.module != MODULES[kind]
                        or record.version != core
                        or not any(
                            d.name == "outerspace-apizr" and d.version == core
                            for d in record.dependencies
                        )
                    ):
                        raise PluginError("plugin_incompatible")
                except (PluginError, PrerequisiteMissing):
                    checks.add(
                        f"{kind}_plugin_active",
                        "fail",
                        "Plugin identity, version or interpreter is incompatible.",
                        "Select an intact official installation matching the core version.",
                    )
                    continue
                records[kind] = record
                checks.add(
                    f"{kind}_plugin_active",
                    "pass",
                    f"Official plugin {record.version}: active inventory and interpreter binding valid.",
                )
            if inventory != store.read_inventory(
                root
            ) or state != activation.validated_activations(root, inventory):
                raise PluginError("inventory_changed")
        checks.add(
            "plugin_store",
            "pass",
            "Selected store metadata is consistent; no lock or plugin execution.",
        )
    except (PluginError, OSError, ValueError, RuntimeError):
        records.clear()
        checks.add(
            "plugin_store",
            "fail",
            "Explicit plugin store unavailable, unsafe or changed.",
            "Pass --plugins-dir pointing to an existing intact isolated store.",
        )
        for kind in requested:
            if not any(c.code == f"{kind}_plugin_active" for c in checks.items):
                checks.add(
                    f"{kind}_plugin_active", "fail", "No validated active installation."
                )
    return records


def doctor(
    *,
    project: str | Path = "apizr.toml",
    operator_policy: str | Path | OperatorPolicy | None = None,
    profiles: tuple[Profile, ...] = ("core",),
    plugins_dir: str | Path | None = None,
    delivery_request: str | Path | None = None,
    bundle: str | Path | None = None,
) -> DoctorResult:
    if (
        not profiles
        or any(p not in PROFILES for p in profiles)
        or (delivery_request is not None and "delivery" not in profiles)
        or (bundle is not None and "clients" not in profiles)
    ):
        raise ValueError("doctor_arguments_invalid")
    checks = Checks()
    try:
        validate_python_target(sys.version_info[:2])
        checks.add(
            "python",
            "pass",
            f"Python {sys.version_info.major}.{sys.version_info.minor} is supported.",
        )
    except ValueError:
        checks.add(
            "python",
            "fail",
            "Unsupported Python interpreter.",
            "Use an interpreter in the supported package range.",
        )
    core = ""
    try:
        core = version("outerspace-apizr")
        if len(core) > 64 or not all(c.isalnum() or c in ".!+-_" for c in core):
            raise ValueError()
        checks.add("core_package", "pass", f"outerspace-apizr {core}")
    except (PackageNotFoundError, ValueError):
        checks.add(
            "core_package", "fail", "Core package metadata unavailable or invalid."
        )
    config = None
    try:
        config = load_project(project)
        checks.add("project", "pass", "apizr.project/v1 valid.")
        with directory_fd(config.root):
            for root in config.scan.source_roots:
                with directory_fd(config.root / root):
                    pass
        checks.add(
            "source_root",
            "pass",
            "Configured source directories are accessible without scanning.",
        )
        checks.add("scan_policy", "pass", "Existing ScanPolicy validated.")
    except (ValueError, OSError, RecursionError):
        checks.add(
            "project" if config is None else "source_root",
            "fail",
            "Invalid project or unsafe/inaccessible source root.",
            "Check --project and its explicit root/source_roots settings.",
        )
    for code, model, path in (
        (
            "readiness_policy",
            RepositoryReadinessPolicy,
            config.readiness_policy if config else None,
        ),
        ("exposure_policy", ExposurePolicy, config.exposure_policy if config else None),
    ):
        if path is None:
            checks.add(code, "skip", "No policy configured.")
            continue
        try:
            policy = load_json(path, model)
            checks.add(code, "pass", "Current policy schema valid.")
            if isinstance(policy, ExposurePolicy):
                empty = (
                    not policy.selection.include
                    and not policy.selection.include_all_ready
                )
                checks.add(
                    "exposure_selection",
                    "warn" if empty else "pass",
                    "No capabilities selected yet."
                    if empty
                    else "Explicit selection configured; capability eligibility is not analyzed.",
                    "Review capability IDs and edit .apizr/policies/exposure.json explicitly."
                    if empty
                    else "",
                )
        except (ValueError, OSError, RecursionError):
            checks.add(
                code,
                "fail",
                "Configured policy is invalid or unavailable.",
                "Correct the selected policy file using its existing schema.",
            )
    authority = None
    if operator_policy is None:
        checks.add(
            "operator_policy",
            "warn",
            "No operator policy supplied; none discovered.",
            "Pass --operator-policy with your explicitly selected local policy.",
        )
    else:
        try:
            authority = (
                OperatorPolicy.model_validate_json(
                    operator_policy.model_dump_json(by_alias=True), strict=True
                )
                if isinstance(operator_policy, OperatorPolicy)
                else load_json(Path(operator_policy), OperatorPolicy)
            )
            checks.add(
                "operator_policy", "pass", "Explicit operator policy schema valid."
            )
        except (ValueError, OSError, RecursionError):
            checks.add(
                "operator_policy",
                "fail",
                "Explicit operator policy is invalid or unavailable.",
            )
    if config is None:
        checks.add(
            "analysis_authority",
            "skip",
            "A valid project is required for an exact-root decision.",
        )
    elif authority is None:
        checks.add(
            "analysis_authority",
            "warn" if operator_policy is None else "fail",
            "Analysis authority is not established.",
            "Pass a valid --operator-policy authorizing this exact local root.",
        )
    else:
        try:
            os.close(open_analysis_root(absolute_path(config.root), authority))
            checks.add(
                "analysis_authority",
                "pass",
                "Existing source admission authorizes this exact local root.",
            )
        except (AuthorizationDenied, ValueError, OSError):
            checks.add(
                "analysis_authority",
                "fail",
                "Existing source admission refused the selected root.",
                "Review the exact root and explicit source.analyze grant.",
            )
    requested = tuple(
        p
        for p in ("mcp", "oci", "attest")
        if p in profiles or ("delivery" in profiles and p in ("oci", "attest"))
    )
    request = None
    if "delivery" in profiles:
        from apizr.mcp_session import load_delivery_request

        try:
            if delivery_request is None:
                raise ValueError()
            request = load_delivery_request(absolute_path(Path(delivery_request)))
            checks.add(
                "delivery_request",
                "pass",
                "BatchRequest and shared immutable build identities valid.",
            )
            if all(d.proof is None for d in request.destinations):
                requested = tuple(p for p in requested if p != "attest")
        except (ValueError, OSError, RecursionError):
            checks.add(
                "delivery_request",
                "fail",
                "Explicit BatchRequest missing, invalid or unavailable.",
                "Pass --delivery-request with an existing qualified local request.",
            )
    records = (
        active_plugins(
            Path(plugins_dir) if plugins_dir is not None else None,
            core,
            requested,
            checks,
        )
        if requested
        else {}
    )
    for kind in ("mcp", "oci", "delivery", "clients"):
        if kind not in profiles and not (kind == "oci" and "delivery" in profiles):
            checks.add(f"{kind}_profile", "skip", "Profile not requested.")
    if "oci" in profiles or "delivery" in profiles:
        checks.add(
            "docker_runtime",
            "skip",
            "Docker/registry availability is not probed; no tool is invoked.",
        )
    if request is not None:
        from .delivery import check_delivery

        check_delivery(request, records, authority, checks)
    if "clients" in profiles:
        found = available("yaml")
        checks.add(
            "clients_extra_available",
            "pass" if found else "fail",
            "Optional clients functionality available."
            if found
            else "Optional clients functionality missing.",
            ""
            if found
            else f"Install outerspace-apizr[clients]=={core} from matching available artifacts.",
        )
        if bundle is not None:
            from apizr.client_collections import ClientError, plan_client_collection

            try:
                plan_client_collection(bundle)
                checks.add(
                    "clients_bundle",
                    "pass",
                    "Existing REST bundle verified without output generation.",
                )
            except (ClientError, ValueError, OSError):
                checks.add(
                    "clients_bundle",
                    "fail",
                    "Explicit REST bundle invalid or unavailable.",
                )
    return DoctorResult(checks=tuple(checks.items))
