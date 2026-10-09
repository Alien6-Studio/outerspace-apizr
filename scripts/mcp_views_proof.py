"""Real SDK proof for bounded repository views from installed core/plugin bytes."""

import argparse
import json
from pathlib import Path
from typing import Any

import anyio
import jsonschema
from mcp import Client, StdioServerParameters

from apizr.exposure.scope import required_evidence
from apizr.graph import analyze_repository
from apizr.graph.serialization import graph_digest
from apizr.repository.serialization import catalog_digest
from apizr.repository_readiness import assess_repository
from apizr.repository_readiness.serialization import report_digest
from apizr.workspace.operator_policy import load_operator_policy


def fixture(root: Path, reverse: bool = False) -> tuple[Path, Path]:
    sources = {
        "pipeline/__init__.py": "",
        "config.py": "from pipeline import missing\n\ndef scale(value: float) -> float:\n    return missing(value)\n",
        "features.py": "from config import scale\n\ndef _normalize(value: float) -> float:\n    return scale(value)\n",
        "serving.py": "from features import _normalize\n\ndef predict(value: float) -> float:\n    return _normalize(value)\n",
        "model.py": 'from typing import TypedDict, Required, NotRequired\nfrom pipeline.step000 import _step\n\nclass Features(TypedDict):\n    age: int\n    score: float\n\nclass Input(TypedDict, total=False):\n    features: Required[Features]\n    note: NotRequired[str]\n\ndef predict(payload: Input) -> float:\n    return _step(payload["features"]["score"])\n',
        "experiments/__init__.py": "",
        "experiments/broken.py": "@replace\ndef broken(value: int):\n    yield value\n",
        "experiments/conditional.py": "if enabled:\n    def candidate(value: int) -> int:\n        return value\n",
        "experiments/ambiguous.py": "def repeated(value: int) -> int:\n    return value\n\ndef repeated(value: str) -> str:\n    return value\n",
    }
    for i in range(60):
        body = "    return value\n" if i == 59 else "    return next_step(value)\n"
        prefix = (
            ""
            if i == 59
            else f"from pipeline.step{i + 1:03d} import _step as next_step\n\n"
        )
        sources[f"pipeline/step{i:03d}.py"] = (
            prefix + "def _step(value: float) -> float:\n" + body
        )
    root.mkdir(parents=True, exist_ok=True)
    for path, text in sorted(sources.items(), reverse=reverse):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    project = root / "apizr.toml"
    project.write_text('schema_version = "apizr.project/v1"\nroot = "."\n')
    operator = root.parent / (root.name + "-operator.json")
    operator.write_text(
        json.dumps(
            {
                "schema": "apizr.operator-policy/v1",
                "grants": [
                    {
                        "adapter": "repository",
                        "operation": "analyze",
                        "target": {"kind": "local", "root": str(root.absolute())},
                        "permissions": ["source.analyze"],
                    }
                ],
            }
        )
    )
    return project, operator


def serialized_bytes(value: Any) -> int:
    """Match the MCP server's structured response limit accounting exactly."""
    return len(json.dumps(value).encode("utf-8"))


async def prove(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    project, operator_path = fixture(root / "views-project")
    authority = load_operator_policy(operator_path)
    evidence = analyze_repository(project.parent, operator_policy=authority)
    report = assess_repository(evidence.catalog, evidence.graph)
    identity = {
        "repository_digest": report.repository_digest.model_dump(mode="json"),
        "catalog_digest": catalog_digest(evidence.catalog).model_dump(mode="json"),
        "graph_digest": graph_digest(evidence.graph).model_dump(mode="json"),
    }
    ready_identity = {
        **identity,
        "repository_readiness_digest": report_digest(report).model_dump(mode="json"),
        "readiness_policy_digest": report.policy_digest.model_dump(mode="json"),
    }
    digest = report.repository_digest.value
    target_id = "python:model:predict"
    selection = {
        "selection": {"include": ["python:serving:predict"]},
        "interfaces": ["rest", "mcp"],
        "execution": {"allowed": ["direct"]},
    }

    def target(bound: int | None = None) -> StdioServerParameters:
        args = ["serve"] if "server_python" in config else ["mcp", "serve"]
        command = (
            config["server_python"] if "server_python" in config else config["cli"]
        )
        if "server_python" in config:
            args = ["-I", "-m", "apizr_mcp", *args]
        else:
            args += ["--plugins-dir", config["store"]]
        args += ["--project", str(project), "--operator-policy", str(operator_path)]
        if bound is not None:
            args += ["--max-response-bytes", str(bound)]
        return StdioServerParameters(
            command=command, args=args, cwd=root, env={"PYTHONDONTWRITEBYTECODE": "1"}
        )

    results: dict[str, Any] = {}
    for mode in ("auto", "legacy"):
        entry: dict[str, Any] = {}
        async with Client(target(), mode=mode, read_timeout_seconds=30) as client:
            assert client.protocol_version == (
                "2026-07-28" if mode == "auto" else "2025-11-25"
            )
            tools = (await client.list_tools()).tools
            assert {t.name for t in tools} == {
                "apizr_analyze",
                "apizr_readiness",
                "apizr_plan_exposure",
            }
            schemas = {t.name: t.output_schema for t in tools}
            for tool in tools:
                assert tool.input_schema["additionalProperties"] is False
                assert tool.output_schema and tool.output_schema["type"] == "object"
                properties = tool.input_schema["properties"]
                assert {"expected_repository_digest", "offset", "limit"} <= set(
                    properties
                )
                if tool.name != "apizr_plan_exposure":
                    assert {"view", "capability_id", "module"} <= set(properties)
                    assert "policy" not in properties
                else:
                    assert "policy" in properties and "view" not in properties
            entry["protocol"] = client.protocol_version
            entry["tools"] = [t.model_dump(mode="json", by_alias=True) for t in tools]

            async def call(
                name: str,
                arguments: dict[str, Any],
                code: str | None = None,
                *,
                schemas: dict[str, Any] = schemas,
            ) -> dict[str, Any]:
                response = await client.call_tool(name, arguments)
                value = response.structured_content
                assert isinstance(value, dict)
                if code is None:
                    assert not response.is_error, value
                    jsonschema.validate(value, schemas[name])
                else:
                    assert response.is_error and value["error"]["code"] == code, value
                assert str(project.parent) not in json.dumps(value)
                return value

            full = {}
            for name in ("apizr_analyze", "apizr_readiness"):
                value = await call(name, {})
                assert value == await call(name, {"view": "full"})
                full[name] = value
                entry[name + "_full_bytes"] = serialized_bytes(value)
                if name == "apizr_analyze":
                    assert set(value) == {"repository_digest", "catalog", "graph"}
                    from apizr.graph.serialization import graph_bytes
                    from apizr.repository.serialization import catalog_bytes

                    assert value["catalog"] == json.loads(
                        catalog_bytes(evidence.catalog)
                    )
                    assert value["graph"] == json.loads(graph_bytes(evidence.graph))
                else:
                    from apizr.repository_readiness.serialization import report_bytes

                    assert set(value) == {"repository_digest", "report", "exit_code"}
                    assert value["report"] == json.loads(report_bytes(report))
                summary = await call(name, {"view": "summary"})
                assert summary["identity"] == (
                    identity if name == "apizr_analyze" else ready_identity
                )
                size = serialized_bytes(summary)
                reduction = 100 * (1 - size / serialized_bytes(value))
                assert reduction >= 75
                assert (
                    "catalog" not in summary
                    and "graph" not in summary
                    and "report" not in summary
                )
                entry[name + "_summary"] = {
                    "value": summary,
                    "bytes": size,
                    "reduction_percent": reduction,
                }
                detail = await call(
                    name, {"view": "detail", "capability_id": target_id}
                )
                assert detail["focus"]["capability_id"] == target_id
                assert detail["identity"] == (
                    identity if name == "apizr_analyze" else ready_identity
                )
                assert (
                    detail["focus"]["local_readiness"]["dimensions"]["inputs"]["state"]
                    == "ready"
                )
                assert "experiments.broken" not in json.dumps(detail)
                size = serialized_bytes(detail)
                reduction = 100 * (1 - size / serialized_bytes(value))
                assert reduction >= 50
                entry[name + "_detail"] = {
                    "value": detail,
                    "bytes": size,
                    "reduction_percent": reduction,
                }

            module = await call(
                "apizr_readiness", {"view": "detail", "module": "serving"}
            )
            assert module["focus"]["module"] == "serving"
            assert any(
                r["kind"] == "capability"
                and r["capability_id"] == "python:serving:predict"
                for r in module["records"]
            )
            entry["module_detail"] = module
            records = []
            offset = 0
            pages = 0
            while True:
                detail = await call(
                    "apizr_readiness",
                    {
                        "view": "detail",
                        "capability_id": target_id,
                        "offset": offset,
                        "limit": 200,
                        "expected_repository_digest": digest,
                    },
                )
                assert detail["identity"] == ready_identity
                records += detail["records"]
                pages += 1
                if detail["page"]["complete"]:
                    assert len(records) == detail["page"]["total"]
                    break
                offset = detail["page"]["next_offset"]
            keys = [json.dumps(r, sort_keys=True) for r in records]
            assert len(set(keys)) == len(keys)
            authority_ids = set(
                required_evidence(
                    evidence.catalog, evidence.graph, report, (target_id,)
                )
                .roots[target_id]
                .required_ids
            ) - {target_id}
            assert {
                r["id"] for r in records if r["kind"] == "dependency"
            } == authority_ids
            assert all(not r["exposed"] for r in records if r["kind"] == "dependency")
            entry["pagination"] = {
                "pages": pages,
                "records": len(records),
                "dependencies": len(authority_ids),
                "duplicates": 0,
                "missing_dependencies": 0,
            }

            refusal = await call(
                "apizr_plan_exposure", {"policy": selection}, "exposure_refused"
            )
            localized = [
                d
                for d in refusal["error"]["diagnostics"]
                if d["evidence_code"] == "APIZR-GRAPH-002"
            ]
            assert (
                localized
                and localized[0]["action"] == "fix_import"
                and localized[0]["source_path"] == "config.py"
                and localized[0]["line"] == 1
            )
            entry["refusal"] = refusal
            plan_page = await call(
                "apizr_plan_exposure",
                {"policy": selection, "limit": 2},
                "exposure_refused",
            )
            assert plan_page["error"]["page"]["total"] == len(
                refusal["error"]["diagnostics"]
            )
            entry["refusal_page"] = plan_page
            allowed = {
                **selection,
                "selection": {"include": [target_id]},
                "execution": {"allowed": ["local-process", "oci-container"]},
            }
            plan = await call("apizr_plan_exposure", {"policy": allowed})
            assert [c["capability_id"] for c in plan["capabilities"]] == [target_id]
            entry["independent_plan"] = {
                "schema_version": plan["schema_version"],
                "selected": target_id,
            }
            for args in (
                {"view": "summary"},
                {"view": "detail", "module": "model"},
                {"view": "detail", "capability_id": target_id},
            ):
                await call(
                    "apizr_readiness",
                    {**args, "expected_repository_digest": "0" * 64},
                    "repository_changed",
                )
            for args in (
                {"view": "detail"},
                {"view": "detail", "module": "model", "capability_id": target_id},
                {"view": "summary", "root": "/"},
                {"view": "detail", "module": "model", "offset": 1},
                {"view": "detail", "module": "model", "limit": "10"},
            ):
                await call("apizr_analyze", args, "invalid_arguments")
            await call(
                "apizr_analyze",
                {"view": "detail", "module": "missing"},
                "unknown_module",
            )
            await call(
                "apizr_readiness",
                {"view": "detail", "capability_id": "python:model:missing"},
                "unknown_capability",
            )
            changed = project.parent / "model.py"
            original = changed.read_bytes()
            changed.write_bytes(original + b"\n# changed between pages\n")
            try:
                await call(
                    "apizr_readiness",
                    {
                        "view": "detail",
                        "capability_id": target_id,
                        "offset": 200,
                        "expected_repository_digest": digest,
                    },
                    "repository_changed",
                )
                fresh = await call("apizr_analyze", {"view": "summary"})
                assert (
                    fresh["identity"]["repository_digest"]
                    != identity["repository_digest"]
                )
            finally:
                changed.write_bytes(original)
            entry["repository_change_between_pages"] = "repository_changed"
            assert [
                t.model_dump(mode="json", by_alias=True)
                for t in (await client.list_tools()).tools
            ] == entry["tools"]
            # The SDK validates successful responses by fetching tools/list;
            # keep that measured listing below the operator's small bound too.
            bound = serialized_bytes(entry["tools"]) + 8192
            assert bound < min(
                entry["apizr_analyze_full_bytes"], entry["apizr_readiness_full_bytes"]
            )
        async with Client(target(bound), mode=mode, read_timeout_seconds=30) as client:
            for name in ("apizr_analyze", "apizr_readiness"):
                oversized = await client.call_tool(name, {})
                assert (
                    oversized.is_error
                    and oversized.structured_content["error"]["code"]
                    == "response_too_large"
                )
                small = await client.call_tool(name, {"view": "summary"})
                assert (
                    not small.is_error and small.structured_content["view"] == "summary"
                )
            entry["small_bound"] = {
                "max_response_bytes": bound,
                "full": "response_too_large",
                "summary": "success",
            }
        results[mode] = entry
        print(
            mode,
            "views, exact schemas, canonical parity, pagination, refusals and response limits: PASS",
            flush=True,
        )
    return {
        "fixture": {
            "files": len(evidence.catalog.sources),
            "capabilities": len(evidence.catalog.capabilities),
        },
        "identity": ready_identity,
        "protocols": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--server-python", type=Path)
    args = parser.parse_args()
    root = args.root.absolute()
    root.mkdir(parents=True, exist_ok=True)
    config = (
        {"server_python": str(args.server_python.absolute())}
        if args.server_python
        else json.loads((root / "installed.json").read_text())
    )
    result = anyio.run(prove, root, config)
    (root / "views-proof.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
