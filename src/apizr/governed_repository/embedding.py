"""Minimal standalone closure copied from reviewed runtime definitions, not analyzers."""

import ast
import json
from hashlib import sha256
from typing import Literal

from apizr.capabilities.model import Digest
from apizr.execution.policy import ExecutionPolicy
from apizr.execution.serialization import canonical_bytes, digest
from apizr.governed.embedding import definition, source
from apizr.interfaces.serialization import json_bytes
from apizr.oci.model import ExecutionPolicyV2, RuntimeImage
from apizr.repository_execution.planner import container_plan, worker_plan
from apizr.repository_interfaces.model import RepositoryInterface

from .model import Bridge, ContainerBundle, ExecutionBundle, PlanArtifact

MODULES = (
    "capabilities/model.py",
    "capabilities/types.py",
    "interfaces/model.py",
    "interfaces/serialization.py",
    "interfaces/runtime.py",
    "execution/policy.py",
    "execution/invocation.py",
    "execution/protocol.py",
    "execution/serialization.py",
    "oci/docker.py",
    "oci/provider.py",
    "repository_interfaces/model.py",
    "repository_execution/model.py",
    "repository_execution/planner.py",
    "repository_execution/supervisor.py",
    "repository_execution/worker.py",
    "repository_execution/docker.py",
    "governed_repository/model.py",
    "governed_repository/runtime.py",
)


def declaration(path: str, name: str) -> str:
    original = source(path)
    node = next(
        n
        for n in ast.parse(original).body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)
    )
    return "\n".join(original.splitlines()[node.lineno - 1 : node.end_lineno]) + "\n"


def runtime_files(transport: Literal["rest", "mcp"]) -> dict[str, bytes]:
    modules = {
        name: source(name) for name in (*MODULES, f"governed_repository/{transport}.py")
    }
    modules["capabilities/types.py"] = modules["capabilities/types.py"].replace(
        definition("capabilities/types.py", "declared_type"), ""
    )
    modules["generators/rest/model.py"] = (
        "from typing import Literal\nfrom apizr.interfaces.model import InvocationContract\n"
        + definition("generators/rest/model.py", "Endpoint")
    )
    modules["generators/mcp/model.py"] = (
        "from typing import Literal\nfrom pydantic import JsonValue\nfrom apizr.capabilities.types import ValueModel\nfrom apizr.interfaces.model import InvocationContract\n"
        + definition("generators/mcp/model.py", "Protocol")
        + "\n"
        + definition("generators/mcp/model.py", "ToolContract")
    )
    modules["repository/policy.py"] = (
        "from pathlib import PurePosixPath, PureWindowsPath\n"
        + definition("repository/policy.py", "relative_path")
    )
    modules["repository_interfaces/model.py"] = modules[
        "repository_interfaces/model.py"
    ].replace(
        "from apizr.exposure.policy import Interface",
        'Interface = Literal["rest", "mcp"]',
    )
    modules["repository_interfaces/runtime.py"] = (
        "import hashlib\nimport importlib.abc\nimport importlib.util\nimport os\nimport stat\nimport sys\nimport types\nfrom pathlib import Path, PurePosixPath\nfrom typing import Any\nfrom apizr.interfaces.runtime import IntegrityError\n\n"
        + "\n".join(
            definition("repository_interfaces/runtime.py", name)
            for name in ("digest", "read_artifact", "RepositoryLoader")
        )
    )
    modules["execution/model.py"] = (
        "from typing import Literal\nfrom pydantic import JsonValue\nfrom apizr.capabilities.types import ValueModel\n\n"
        + declaration("execution/model.py", "Status")
        + "\n"
        + definition("execution/model.py", "ExecutionResult")
    )
    modules["execution/supervisor.py"] = (
        "import os\nimport selectors\nimport signal\nimport subprocess\nimport time\nfrom collections.abc import Mapping, Sequence\nfrom pathlib import Path\nfrom .model import ExecutionResult\nfrom .policy import Environment\nfrom .protocol import ProtocolError, SizeExceeded, decode, size\n\n"
        + "\n".join(
            definition("execution/supervisor.py", name)
            for name in ("worker_environment", "kill_group", "exchange")
        )
    )
    modules["oci/model.py"] = (
        "from typing import Literal, Self\nfrom pydantic import Field, JsonValue, model_validator\nfrom apizr.capabilities.types import ValueModel\nfrom apizr.execution.model import Status\nfrom apizr.execution.policy import Effects, Environment, Limits, Network, Subprocess\n\n"
        + "\n".join(
            definition("oci/model.py", name)
            for name in ("Resources", "ExecutionPolicyV2", "RuntimeImage")
        )
        + "\n"
        + declaration("oci/model.py", "ContainerStatus")
        + "\n"
        + definition("oci/model.py", "ContainerResult")
    )
    modules["oci/planner.py"] = (
        "from apizr.execution.policy import PolicyRefused\nfrom .model import ExecutionPolicyV2\n\n"
        + definition("oci/planner.py", "check_controls")
    )
    for name in ("oci/docker.py", "oci/provider.py", "repository_execution/docker.py"):
        modules[name] = (
            modules[name]
            .replace(
                "from .model import ContainerPlan, RuntimeImage",
                "from .model import RuntimeImage\nfrom apizr.repository_execution.model import RepositoryContainerPlan as ContainerPlan",
            )
            .replace(
                "from .model import ContainerPlan, ContainerStatus, RuntimeImage",
                "from .model import ContainerStatus, RuntimeImage\nfrom apizr.repository_execution.model import RepositoryContainerPlan as ContainerPlan",
            )
            .replace(
                "from apizr.oci.model import ContainerPlan, RuntimeImage",
                "from apizr.oci.model import RuntimeImage\nfrom apizr.repository_execution.model import RepositoryContainerPlan as ContainerPlan",
            )
        )
    artifacts = {
        "apizr_governed/" + name: text.replace(
            "from apizr.", "from apizr_governed."
        ).encode()
        for name, text in modules.items()
    }
    for name in list(artifacts):
        pieces = name.split("/")[:-1]
        for i in range(1, len(pieces) + 1):
            artifacts.setdefault("/".join(pieces[:i]) + "/__init__.py", b"")
    bootstrap = source("governed/bootstrap.py")
    artifacts["execution/worker.py"] = (
        bootstrap
        + "\nactivate(Path(__file__).resolve().parents[1])\nfrom apizr_governed.repository_execution.worker import main\nmain()\n"
    ).encode()
    entry = "app.py" if transport == "rest" else "server.py"
    artifacts[entry] = (
        bootstrap
        + "\nROOT = Path(__file__).resolve().parent\nactivate(ROOT)\n"
        + (
            "from apizr_governed.governed_repository.rest import create_app\napp = create_app(ROOT)\n"
            if transport == "rest"
            else 'from apizr_governed.governed_repository.mcp import main\nif __name__ == "__main__":\n    main(ROOT)\n'
        )
    ).encode()
    return artifacts


def govern(
    artifacts: dict[str, bytes],
    policy: ExecutionPolicy | ExecutionPolicyV2,
    runtime_image: RuntimeImage | None,
    transport: Literal["rest", "mcp"],
) -> dict[str, bytes]:
    artifacts = dict(artifacts)
    manifest_name = f"apizr-repository-{transport}.json"
    manifest = json.loads(artifacts.pop(manifest_name))
    contract = RepositoryInterface.model_validate_json(
        artifacts["repository-interface.json"]
    )
    plans: dict[str, PlanArtifact] = {}
    for capability in contract.capabilities:
        if isinstance(policy, ExecutionPolicyV2):
            if runtime_image is None:
                raise ValueError("OCI requires explicit runtime image and platform")
            selected_plan = container_plan
            if policy.subprocess.mode == "deny":
                from apizr.subprocess_guard.repository import (
                    container_plan as selected_plan,
                )
            plan = selected_plan(
                contract,
                artifacts["exposure-plan.json"],
                capability.capability_id,
                policy,
                runtime_image,
            )
        else:
            if runtime_image is not None:
                raise ValueError("Runtime image requires OCI policy")
            plan = worker_plan(
                contract,
                artifacts["exposure-plan.json"],
                capability.capability_id,
                policy,
            )
        path = (
            "execution/plans/"
            + sha256(capability.capability_id.encode()).hexdigest()
            + ".json"
        )
        artifacts[path] = canonical_bytes(plan)
        plans[capability.capability_id] = PlanArtifact(path=path, digest=digest(plan))
    artifacts.pop("apizr_runtime.py")
    artifacts.pop("apizr_repository_runtime.py")
    runtime_artifacts = runtime_files(transport)
    if isinstance(policy, ExecutionPolicyV2) and policy.subprocess.mode == "deny":
        from apizr.subprocess_guard.embedding import strict_files

        runtime_artifacts = strict_files(runtime_artifacts, repository=True)
    artifacts.update(runtime_artifacts)
    artifacts["execution/policy.json"] = canonical_bytes(policy)
    artifacts["requirements.txt"] += b"pydantic>=2.12,<3\n"
    fields = Bridge(
        transport=transport,
        repository_interface_digest=digest(contract),
        exposure_plan_digest=contract.exposure_plan_digest,
        contract_digest=Digest.of_bytes(
            json_bytes(manifest["endpoints" if transport == "rest" else "tools"])
        ),
        policy_digest=digest(policy),
        capabilities=dict(sorted(plans.items())),
        artifacts={
            name: Digest.of_bytes(content)
            for name, content in sorted(artifacts.items())
        },
    )
    if isinstance(policy, ExecutionPolicyV2):
        assert runtime_image is not None
        bundle = ContainerBundle(**fields.model_dump(), runtime=runtime_image)
    else:
        bundle = ExecutionBundle(**fields.model_dump())
    artifacts["execution/bundle.json"] = canonical_bytes(bundle)
    manifest["artifacts"] = {
        name: Digest.of_bytes(content).model_dump(mode="json")
        for name, content in sorted(artifacts.items())
    }
    artifacts[manifest_name] = json_bytes(manifest)
    return dict(sorted(artifacts.items()))
