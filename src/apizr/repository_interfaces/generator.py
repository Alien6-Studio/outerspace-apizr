"""Deterministic rendering over retained evidence, with no project filesystem access."""

from collections.abc import Mapping
from importlib.resources import files

from apizr.capabilities.model import Digest
from apizr.execution.policy import ExecutionPolicy
from apizr.exposure import ExposurePlan, ExposurePolicy, plan_bytes, policy_bytes
from apizr.exposure.policy import Interface
from apizr.generators.mcp.generator import REQUIREMENTS as MCP_REQUIREMENTS
from apizr.generators.mcp.model import Protocol, ToolContract
from apizr.generators.mcp.planner import tool_name
from apizr.generators.rest.generator import REQUIREMENTS as REST_REQUIREMENTS
from apizr.generators.rest.model import Endpoint
from apizr.generators.rest.schema import openapi
from apizr.graph import Graph, graph_bytes
from apizr.interfaces.schema import request_schema
from apizr.interfaces.serialization import json_bytes
from apizr.oci.model import ExecutionPolicyV2, RuntimeImage
from apizr.repository import Catalog, catalog_bytes
from apizr.repository.serialization import canonical_bytes
from apizr.repository_readiness import RepositoryReadinessReport, report_bytes

from .model import MCPManifest, RestManifest
from .planner import BundleRefused, plan_repository_interface


def template(name: str) -> bytes:
    source = (
        files("apizr.repository_interfaces").joinpath(name).read_text(encoding="utf-8")
    )
    return (
        source.replace(
            "from apizr.interfaces.runtime import", "from apizr_runtime import"
        )
        .replace(
            "from apizr.repository_interfaces.runtime import",
            "from apizr_repository_runtime import",
        )
        .encode("utf-8")
    )


def render_repository_bundle(
    catalog: Catalog,
    graph: Graph,
    readiness: RepositoryReadinessReport,
    policy: ExposurePolicy,
    exposure: ExposurePlan,
    sources: Mapping[str, bytes],
    *,
    interface: Interface,
    execution_policy: ExecutionPolicy | ExecutionPolicyV2 | None = None,
    runtime_image: RuntimeImage | None = None,
) -> dict[str, bytes]:
    if isinstance(execution_policy, ExecutionPolicyV2):
        if runtime_image is None:
            raise ValueError("OCI requires image and platform")
    elif runtime_image is not None:
        raise ValueError("Runtime image requires OCI policy")
    sources = dict(sources)
    contract = plan_repository_interface(
        catalog,
        graph,
        readiness,
        policy,
        exposure,
        sources,
        interface=interface,
        execution_mode=execution_policy.backend
        if execution_policy is not None
        else "direct",
    )
    contract_bytes = canonical_bytes(contract)
    contract_digest = Digest.of_bytes(contract_bytes)
    artifacts = {
        "repository-interface.json": contract_bytes,
        "capability-catalog.json": catalog_bytes(catalog),
        "capability-graph.json": graph_bytes(graph),
        "repository-readiness.json": report_bytes(readiness),
        "exposure-policy.json": policy_bytes(policy),
        "exposure-plan.json": plan_bytes(exposure),
        "apizr_repository_runtime.py": template("runtime.py"),
        "apizr_runtime.py": files("apizr.interfaces")
        .joinpath("runtime.py")
        .read_bytes(),
    }
    artifacts.update({s.bundle_path: sources[s.source_path] for s in contract.sources})
    pin = repr(contract_digest.model_dump())
    endpoints = tuple(
        Endpoint(**c.invocation.model_dump(), route="/capabilities/" + c.public_name)
        for c in contract.capabilities
    )
    tools = tuple(
        ToolContract(
            **c.invocation.model_dump(),
            tool_name=tool_name(c.capability_id, c.public_name),
            input_schema=request_schema(c.invocation),
        )
        for c in contract.capabilities
    )
    if len({t.tool_name for t in tools}) != len(tools):
        raise BundleRefused("APIZR-BUNDLE-005: public name collision")
    if interface == "rest":
        artifacts["requirements.txt"] = REST_REQUIREMENTS
        document = openapi(endpoints)
        document["info"] = {
            "title": "Apizr Repository REST API",
            "version": "apizr.repository-rest/v1",
        }
        artifacts["openapi.json"] = json_bytes(document)
        artifacts["app.py"] = (
            template("rest_runtime.py")
            + f"\n\napp = create_app(Path(__file__).resolve().parent, {pin})\n".encode()
        )
        manifest = RestManifest(
            repository_interface_digest=contract_digest,
            exposure_plan_digest=contract.exposure_plan_digest,
            sources=contract.sources,
            endpoints=endpoints,
            artifacts={
                name: Digest.of_bytes(content)
                for name, content in sorted(artifacts.items())
            },
        )
    else:
        artifacts["requirements.txt"] = MCP_REQUIREMENTS
        artifacts["mcp-tools.json"] = json_bytes(
            {
                "schema_version": "apizr.repository-mcp/v1",
                "protocol": {"target": Protocol().target},
                "tools": [
                    {
                        "name": t.tool_name,
                        "inputSchema": t.input_schema,
                        "_meta": {"sh.outerspace.apizr/capability-id": t.capability_id},
                        **(
                            {"description": t.description}
                            if t.description is not None
                            else {}
                        ),
                    }
                    for t in tools
                ],
            }
        )
        artifacts["server.py"] = (
            template("mcp_runtime.py")
            + f'\n\nif __name__ == "__main__":\n    main({pin})\n'.encode()
        )
        manifest = MCPManifest(
            repository_interface_digest=contract_digest,
            exposure_plan_digest=contract.exposure_plan_digest,
            sources=contract.sources,
            tools=tools,
            artifacts={
                name: Digest.of_bytes(content)
                for name, content in sorted(artifacts.items())
            },
        )
    artifacts["apizr-repository-" + interface + ".json"] = canonical_bytes(manifest)
    if execution_policy is not None:
        from apizr.governed_repository.embedding import govern

        return govern(artifacts, execution_policy, runtime_image, interface)
    return dict(sorted(artifacts.items()))
