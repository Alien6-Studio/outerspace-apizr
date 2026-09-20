"""Deterministic source embedding of the installed execution implementation."""

import ast
import json
from importlib.resources import files
from typing import Literal

from apizr.capabilities.model import Digest
from apizr.execution import (
    ExecutionPolicy,
    plan,
    plan_bytes,
    plan_digest,
    policy_bytes,
    policy_digest,
)
from apizr.inspection import Inspection
from apizr.interfaces.serialization import json_bytes

from .model import ExecutionBundle, PlanArtifact

# This is the validation/execution dependency closure, not an Apizr installation.
# No analyzer, notebook exporter, legacy pipeline or generator is shipped.
MODULES = (
    "capabilities/model.py",
    "capabilities/types.py",
    "capabilities/serialization.py",
    "readiness/model.py",
    "readiness/serialization.py",
    "interfaces/model.py",
    "interfaces/planner.py",
    "interfaces/schema.py",
    "interfaces/serialization.py",
    "interfaces/runtime.py",
    "execution/model.py",
    "execution/policy.py",
    "execution/planner.py",
    "execution/invocation.py",
    "execution/protocol.py",
    "execution/serialization.py",
    "execution/supervisor.py",
    "execution/worker.py",
    "governed/model.py",
    "governed/runtime.py",
)


def source(path: str) -> str:
    return files("apizr").joinpath(path).read_text(encoding="utf-8")


def definition(path: str, name: str) -> str:
    """Copy the original definition verbatim; never maintain a fork of its logic."""
    original = source(path)
    node = next(
        n
        for n in ast.parse(original).body
        if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == name
    )
    return "\n".join(original.splitlines()[node.lineno - 1 : node.end_lineno]) + "\n"


def runtime_files(transport: Literal["rest", "mcp"]) -> dict[str, bytes]:
    modules = {name: source(name) for name in (*MODULES, f"governed/{transport}.py")}
    # Inspection's model validates linkage; its unrelated analyzer/reporting entry
    # points would pull in the source analyzer and are deliberately not embedded.
    modules["inspection.py"] = (
        "from typing import Literal, Self\nfrom pydantic import model_validator\n"
        "from apizr.capabilities.model import CapabilityDocument, Digest, Severity\n"
        "from apizr.capabilities.types import ValueModel\n"
        "from apizr.capabilities.serialization import document_digest\n"
        "from apizr.readiness.model import ReadinessReport, State\n"
        "from apizr.readiness.serialization import report_digest\n\n"
        + definition("inspection.py", "Inspection")
    )
    modules["capabilities/types.py"] = modules["capabilities/types.py"].replace(
        definition("capabilities/types.py", "declared_type"), ""
    )
    for unused in ("json_schema", "request_schema"):
        modules["interfaces/schema.py"] = modules["interfaces/schema.py"].replace(
            definition("interfaces/schema.py", unused), ""
        )
    artifacts = {
        "apizr_governed/" + name: text.replace(
            "from apizr.", "from apizr_governed."
        ).encode("utf-8")
        for name, text in modules.items()
    }
    for package in (
        "",
        "capabilities/",
        "readiness/",
        "interfaces/",
        "execution/",
        "governed/",
    ):
        artifacts["apizr_governed/" + package + "__init__.py"] = b""
    bootstrap = source("governed/bootstrap.py")
    artifacts["execution/worker.py"] = (
        bootstrap + "\nactivate(Path(__file__).resolve().parents[1])\n"
        "from apizr_governed.execution.worker import main\nmain()\n"
    ).encode("utf-8")
    artifacts["app.py" if transport == "rest" else "server.py"] = (
        bootstrap
        + "\nROOT = Path(__file__).resolve().parent\nactivate(ROOT)\n"
        + (
            "from apizr_governed.governed.rest import create_app\napp = create_app(ROOT)\n"
            if transport == "rest"
            else 'from apizr_governed.governed.mcp import main\nif __name__ == "__main__":\n    main(ROOT)\n'
        )
    ).encode("utf-8")
    return artifacts


def govern(
    artifacts: dict[str, bytes],
    inspection: Inspection,
    source_bytes: bytes,
    executable: bytes,
    policy: ExecutionPolicy,
    transport: Literal["rest", "mcp"],
) -> dict[str, bytes]:
    policy = ExecutionPolicy.model_validate(policy.model_dump(mode="json"))
    # The direct MCP helper is superseded by the single embedded shared binder.
    artifacts.pop("apizr_runtime.py", None)
    manifest_name = f"apizr-{transport}.json"
    manifest = json.loads(artifacts.pop(manifest_name))
    contracts = manifest["capabilities" if transport == "rest" else "tools"]
    plans: dict[str, PlanArtifact] = {}
    for contract in contracts:
        runtime = plan(
            inspection,
            source_bytes,
            contract["capability_id"],
            policy,
            executable=executable,
            check_availability=False,
        )
        path = "execution/plans/" + runtime.interface.name + ".json"
        artifacts[path] = plan_bytes(runtime)
        plans[runtime.capability_id] = PlanArtifact(
            path=path, digest=plan_digest(runtime)
        )
    artifacts.update(runtime_files(transport))
    artifacts["execution/policy.json"] = policy_bytes(policy)
    # Explicit version requirement for the copied typed validation/runtime models.
    artifacts["requirements.txt"] += b"pydantic>=2.12,<3\n"
    bundle = ExecutionBundle(
        transport=transport,
        contract_digest=Digest.of_bytes(json_bytes(contracts)),
        policy_digest=policy_digest(policy),
        capabilities=dict(sorted(plans.items())),
        artifacts={
            name: Digest.of_bytes(content)
            for name, content in sorted(artifacts.items())
        },
    )
    artifacts["execution/bundle.json"] = json_bytes(bundle.model_dump(mode="json"))
    manifest["artifacts"] = {
        name: Digest.of_bytes(content).model_dump(mode="json")
        for name, content in sorted(artifacts.items())
    }
    artifacts[manifest_name] = json_bytes(manifest)
    return dict(sorted(artifacts.items()))
