"""#252: refine bound local imports without widening any other boundary."""

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import anyio
import httpx
import pytest
from analysis_authorization import analysis_policy
from governed.helpers import SERVER, http_server
from mcp import Client, StdioServerParameters

from apizr.compiler import prepare_exposure, render_bundle
from apizr.execution.policy import ExecutionPolicy
from apizr.exposure import ExposurePolicy, ExposureRefused, plan_exposure
from apizr.graph import build_graph
from apizr.inspection import inspect_source
from apizr.interfaces.planner import GenerationRefused, invocation_contract, plan
from apizr.repository import scan_sources
from apizr.repository_execution.planner import worker_plan
from apizr.repository_execution.supervisor import execute
from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_interfaces.planner import plan_repository_interface
from apizr.repository_readiness import (
    RepositoryReadinessPolicy,
    assess_repository,
    validate_report,
)
from apizr.repository_readiness.eligibility import (
    can_generate_interface,
    interface_state,
)

from .conftest import evidence

HELPER = b"def double(value: int) -> int:\n    return value * 2\n"
FACADE = b"from helper import double\n\n\ndef calculate(value: int) -> int:\n    return double(value)\n"
FILES = {"helper.py": HELPER, "facade.py": FACADE}
SELECTED = "python:facade:calculate"


@pytest.mark.parametrize("interface", ["rest", "mcp"])
@pytest.mark.parametrize(
    "source,package",
    [
        (FACADE, False),
        (
            b"import helper\ndef calculate(value: int) -> int: return helper.double(value)\n",
            False,
        ),
        (
            b"import helper as h\ndef calculate(value: int) -> int: return h.double(value)\n",
            False,
        ),
        (
            b"from helper import double as twice\ndef calculate(value: int) -> int: return twice(value)\n",
            False,
        ),
        (
            b"def calculate(value: int) -> int:\n from helper import double\n return double(value)\n",
            False,
        ),
        (FACADE.replace(b"from helper", b"from .helper"), True),
    ],
)
def test_proven_import_forms_keep_local_evidence_and_private_support(
    source, package, interface
):
    prefix = "shop/" if package else ""
    module = "shop.facade" if package else "facade"
    files = {prefix + "helper.py": HELPER, prefix + "facade.py": source}
    if package:
        files["shop/__init__.py"] = b""
    identity = f"python:{module}:calculate"
    values = evidence(files, selected=(identity,))
    catalog, graph, readiness, _, exposure, _ = values
    local = next(s.inspection for s in catalog.sources if s.module == module)
    before = local.model_dump_json()
    selected = next(a for a in readiness.assessments if a.capability_id == identity)
    assert graph.complete and selected.relationships.state == "resolved"
    assert selected.local_readiness == local.readiness.assessments[0]
    assert selected.local_readiness.state.value == "conditional"
    assert {
        r.code.value for r in selected.local_readiness.dimensions.execution.reasons
    } == {"APIZR-READY-015"}
    assert selected.state.value == "ready" and can_generate_interface(selected)
    assert exposure.capability_ids() == (identity,)
    artifacts = render_repository_bundle(*values, interface=interface)
    assert artifacts["source/" + prefix + "helper.py"] == HELPER
    contract = json.loads(artifacts["repository-interface.json"])
    assert [c["capability_id"] for c in contract["capabilities"]] == [identity]
    surface = artifacts["openapi.json" if interface == "rest" else "mcp-tools.json"]
    assert b"helper.double" not in surface
    assert local.model_dump_json() == before
    with pytest.raises(GenerationRefused, match="APIZR-READY-015"):
        plan(local, source, select=[identity])


@pytest.mark.parametrize("mode", ["direct", "local-process", "oci-container"])
def test_static_eligibility_does_not_probe_execution_mode(mode):
    values = evidence(FILES, selected=(SELECTED,), modes=(mode,))
    assert (
        plan_repository_interface(*values, interface="rest", execution_mode=mode)
        .capabilities[0]
        .capability_id
        == SELECTED
    )
    hard = assess_repository(
        values[0], values[1], policy=RepositoryReadinessPolicy(require_interface=True)
    )
    assert (
        next(a for a in hard.assessments if a.capability_id == SELECTED).state.value
        == "ready"
    )


@pytest.mark.parametrize(
    "facade,helper,extra",
    [
        (
            FACADE.replace(b"double\n", b"missing\n").replace(
                b"double(value)", b"missing(value)"
            ),
            HELPER,
            {},
        ),
        (FACADE, HELPER + b"def double(value: int) -> int: return value\n", {}),
        (FACADE, HELPER + b"double = 3\n", {}),
        (FACADE, b"dangerous = load_something()\n" + HELPER, {}),
        (FACADE, HELPER + b"import definitely_missing_apizr_dependency\n", {}),
        (
            FACADE.replace(b"from helper import double", b"from helper import *"),
            HELPER,
            {},
        ),
        (
            b"import helper\nhelper = 1\ndef calculate(value: int) -> int: return helper.double(value)\n",
            HELPER,
            {},
        ),
        (
            b"def calculate(value: int) -> int: return __import__('helper').double(value)\n",
            HELPER,
            {},
        ),
        (FACADE.replace(b"from helper", b"from ..helper"), HELPER, {}),
        (FACADE, b"@decorate\n" + HELPER, {}),
        (
            b"from helper import double\ndef calculate(value: Missing) -> int: return double(value)\n",
            HELPER,
            {},
        ),
        (
            b"from helper import double\nsetup = load_something()\ndef calculate(value: int) -> int: return double(value)\n",
            HELPER,
            {},
        ),
        (
            b"from helper import double\n@decorate\ndef calculate(value: int) -> int: return double(value)\n",
            HELPER,
            {},
        ),
        (FACADE + b"globals()['other'] = 1\n", HELPER, {}),
        (
            b"if condition:\n from helper import double\ndef calculate(value: int) -> int: return double(value)\n",
            HELPER,
            {},
        ),
    ],
)
def test_unproven_or_unrelated_blockers_remain_refused(facade, helper, extra):
    with pytest.raises(ExposureRefused) as error:
        evidence(
            {"facade.py": facade, "helper.py": helper, **extra}, selected=(SELECTED,)
        )
    assert any(d.capability_id == SELECTED for d in error.value.diagnostics)


def test_external_dependency_is_not_admitted_even_with_complete_graph():
    files = {
        "facade.py": b"import definitely_missing_apizr_dependency\ndef calculate(value: int) -> int: return value\n"
    }
    catalog = scan_sources(files.items())
    graph = build_graph(catalog, files)
    report = assess_repository(catalog, graph)
    assert graph.complete and graph.imports[0].names[0].resolution == "external"
    assert report.assessments[0].state.value == "conditional"
    assert not can_generate_interface(report.assessments[0])
    with pytest.raises(ExposureRefused):
        plan_exposure(
            catalog,
            graph,
            report,
            policy=ExposurePolicy.model_validate(
                {
                    "selection": {"include": [SELECTED]},
                    "interfaces": ["rest", "mcp"],
                    "execution": {"allowed": ["local-process", "oci-container"]},
                }
            ),
        )


@pytest.mark.parametrize(
    "initializer",
    [
        b"raise RuntimeError('MUST NOT EXECUTE')\n",
        b"setup = load_something()\n",
        b'"""No callable initialization evidence in v1."""\n',
    ],
)
def test_nonempty_initializer_without_readiness_evidence_remains_conditional(
    initializer,
):
    with pytest.raises(ExposureRefused):
        evidence(
            {
                "shop/__init__.py": initializer,
                "shop/helper.py": HELPER,
                "shop/facade.py": FACADE.replace(b"from helper", b"from .helper"),
            },
            selected=("python:shop.facade:calculate",),
        )


def test_private_helper_need_not_have_public_json_inputs_and_effects_are_not_inferred():
    values = evidence(
        {
            "helper.py": HELPER.replace(b"value: int", b"value: bytes"),
            "facade.py": FACADE,
        },
        selected=(SELECTED,),
    )
    by_id = {a.capability_id: a for a in values[2].assessments}
    assert by_id["python:helper:double"].state.value == "unsupported"
    assert by_id[SELECTED].state.value == "ready"
    assert (
        by_id[SELECTED].effects.model_dump()
        == by_id[SELECTED].local_readiness.effects.model_dump()
    )
    assert all(
        effect["value"] == "unknown"
        for effect in by_id[SELECTED].effects.model_dump().values()
    )


def test_unused_helper_body_uncertainty_is_not_module_initialization():
    values = evidence(
        {
            "helper.py": HELPER + b"def unused(): return __import__('unknown')\n",
            "facade.py": FACADE,
        },
        selected=(SELECTED,),
    )
    assert (
        next(
            a for a in values[2].assessments if a.capability_id == SELECTED
        ).state.value
        == "ready"
    )


def test_shared_lowering_requires_matching_ir_evidence_and_supported_execution():
    inspected = inspect_source(HELPER, module_name="helper")
    unrelated = inspect_source(HELPER, module_name="other")
    with pytest.raises(ValueError, match="disagrees"):
        invocation_contract(
            inspected.capability_ir.capabilities[0], unrelated.readiness.assessments[0]
        )
    generator = inspect_source(b"def stream(): yield 1\n", module_name="helper")
    with pytest.raises(ValueError, match="execution"):
        invocation_contract(
            generator.capability_ir.capabilities[0], generator.readiness.assessments[0]
        )


def test_unrelated_global_ambiguity_does_not_block_selected_helpers():
    values = evidence(
        {**FILES, "unrelated.py": b"def duplicate(): pass\ndef duplicate(): pass\n"},
        selected=(SELECTED,),
    )
    assert values[4].capability_ids() == (SELECTED,)
    assert values[0].exit_code == 1 and not values[1].complete


@pytest.mark.parametrize(
    "field",
    [
        "path",
        "line",
        "end_line",
        "column",
        "end_column",
        "source",
        "target",
        "availability",
        "kind",
        "dependencies",
        "imports",
        "external",
        "conditional",
        "empty",
    ],
)
def test_import_proof_requires_exact_retained_facts(field):
    values = evidence(FILES, selected=(SELECTED,))
    assessment = next(a for a in values[2].assessments if a.capability_id == SELECTED)
    facts = assessment.relationships
    if field == "dependencies":
        facts = facts.model_copy(update={"dependencies": ()})
    elif field in {"imports", "external", "conditional", "empty"}:
        declaration = facts.imports[0]
        imports = (
            ()
            if field == "imports"
            else (
                declaration.model_copy(update={"names": ()})
                if field == "empty"
                else declaration.model_copy(update={"availability": "conditional"})
                if field == "conditional"
                else declaration.model_copy(
                    update={
                        "names": (
                            declaration.names[0].model_copy(
                                update={"resolution": "external"}
                            ),
                        )
                    }
                ),
            )
        )
        facts = facts.model_copy(update={"imports": imports})
    else:
        changes = {
            "path": "wrong.py",
            "line": 99,
            "end_line": 99,
            "column": 99,
            "end_column": 99,
            "source": "wrong",
            "target": "wrong",
            "availability": "conditional",
            "kind": "references_capability",
        }
        facts = facts.model_copy(
            update={
                "module_imports": tuple(
                    e.model_copy(update={field: changes[field]})
                    for e in facts.module_imports
                )
            }
        )
    assert (
        interface_state(assessment.local_readiness, assessment.source_path, facts).value
        == "conditional"
    )
    forged = assessment.model_copy(update={"relationships": facts})
    report = values[2].model_copy(
        update={
            "assessments": tuple(
                forged if a.capability_id == SELECTED else a
                for a in values[2].assessments
            )
        }
    )
    with pytest.raises(ValueError):
        validate_report(report, values[0], values[1])


def test_retained_bytes_generation_and_relocation_without_reanalysis(
    tmp_path, monkeypatch
):
    outputs = []
    for name in ("one", "other/location"):
        root = tmp_path / name
        root.mkdir(parents=True)
        for path, content in FILES.items():
            (root / path).write_bytes(content)
        prepared = prepare_exposure(
            root,
            operator_policy=analysis_policy(root),
            policy=ExposurePolicy.model_validate(
                {
                    "selection": {"include": [SELECTED]},
                    "interfaces": ["rest", "mcp"],
                    "execution": {"allowed": ["direct"]},
                }
            ),
            readiness_policy=RepositoryReadinessPolicy.model_validate(
                {"execution": {"modes": ["direct"]}}
            ),
        )
        (root / "helper.py").write_text("raise RuntimeError('CHANGED')\n")
        parse = ast.parse
        read_bytes = Path.read_bytes

        def annotations_only(source, *args, parse=parse, **kwargs):
            assert kwargs.get("mode") == "eval"
            return parse(source, *args, **kwargs)

        def forbidden(*args, **kwargs):
            raise AssertionError("Reanalysis or host package lookup")

        def retained_source_only(path, read_bytes=read_bytes, root=root):
            assert not path.is_relative_to(root), "Project source re-read"
            return read_bytes(path)

        with monkeypatch.context() as isolated:
            isolated.setattr(ast, "parse", annotations_only)
            isolated.setattr(Path, "read_bytes", retained_source_only)
            isolated.setattr(importlib.util, "find_spec", forbidden)
            outputs.append(
                {
                    transport: render_bundle(prepared, interface=transport)
                    for transport in ("rest", "mcp")
                }
            )
        assert outputs[-1]["rest"]["source/helper.py"] == HELPER
    assert outputs[0] == outputs[1]
    assert all(
        str(tmp_path).encode() not in data
        for artifacts in outputs[0].values()
        for data in artifacts.values()
    )


def test_real_direct_rest_and_official_mcp_stdio(tmp_path, monkeypatch):
    values = evidence(FILES, selected=(SELECTED,))
    for interface in ("rest", "mcp"):
        write_bundle(
            tmp_path / interface, render_repository_bundle(*values, interface=interface)
        )
    monkeypatch.setattr(
        "governed.helpers.SERVER",
        SERVER.replace(
            "root=Path(sys.argv[1]).resolve()",
            "root=Path(sys.argv[1]).resolve()\nsys.path.insert(0,str(root))",
        ),
    )
    with (
        http_server(tmp_path / "rest", "rest") as (url, process),
        httpx.Client(base_url=url, timeout=10) as client,
    ):
        result = client.post("/capabilities/facade.calculate", json={"value": 3})
        assert result.status_code == 200 and result.json() == 6
        assert (
            client.post("/capabilities/helper.double", json={"value": 3}).status_code
            == 404
        )
        assert set(client.get("/openapi.json").json()["paths"]) == {
            "/capabilities/facade.calculate",
            "/health",
        }
        assert process.poll() is None

    async def check():
        async with Client(
            StdioServerParameters(
                command=sys.executable,
                args=[str(tmp_path / "mcp/server.py")],
                cwd=tmp_path / "mcp",
            ),
            read_timeout_seconds=10,
        ) as client:
            assert [t.name for t in (await client.list_tools()).tools] == [
                "facade.calculate"
            ]
            result = await client.call_tool("facade.calculate", {"value": 3})
            assert not result.is_error and result.structured_content == {"result": 6}
            assert json.loads(result.content[0].text) == result.structured_content

    anyio.run(check)


def test_repository_local_worker_resolves_private_helper():
    from apizr.exposure import plan_bytes

    values = evidence(FILES, selected=(SELECTED,), modes=("local-process",))
    contract = plan_repository_interface(
        *values, interface="rest", execution_mode="local-process"
    )
    exposure = plan_bytes(values[4])
    worker = worker_plan(contract, exposure, SELECTED, ExecutionPolicy())
    sources = {s.bundle_path: values[-1][s.source_path] for s in contract.sources}
    result = execute(worker, exposure, sources, {"value": 3})
    assert result.status == "success" and result.value == 6


def test_analysis_and_generation_never_execute_project_or_probe_runtime(tmp_path):
    for path, content in {
        **FILES,
        "unrelated.py": b"raise RuntimeError('MUST NOT EXECUTE')\n",
    }.items():
        (tmp_path / path).write_bytes(content)
    probe = """import sys, json
from pathlib import Path
from apizr.compiler import prepare_exposure, render_bundle
from apizr.operator_policy import OperatorPolicy
from apizr.exposure import ExposurePolicy
from apizr.repository_readiness import RepositoryReadinessPolicy
root = Path(sys.argv[1]).resolve()
def audit(event, args):
 if event in {'subprocess.Popen', 'os.system', 'socket.connect'}: raise AssertionError(event)
 if event == 'exec' and str(root) in args[0].co_filename: raise AssertionError('project execution')
sys.addaudithook(audit)
authority = OperatorPolicy.model_validate_json(json.dumps({'schema': 'apizr.operator-policy/v1', 'grants': [{'adapter': 'repository', 'operation': 'analyze', 'target': {'kind': 'local', 'root': str(root)}, 'permissions': ['source.analyze']}]}))
prepared = prepare_exposure(root, operator_policy=authority, policy=ExposurePolicy.model_validate({'selection': {'include': ['python:facade:calculate']}, 'interfaces': ['rest', 'mcp'], 'execution': {'allowed': ['direct']}}), readiness_policy=RepositoryReadinessPolicy.model_validate({'execution': {'modes': ['direct']}}))
for interface in ('rest', 'mcp'): assert render_bundle(prepared, interface=interface)
assert 'helper' not in sys.modules and 'facade' not in sys.modules and 'unrelated' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", probe, str(tmp_path)], capture_output=True, timeout=20
    )
    assert result.returncode == 0, result.stderr.decode()
