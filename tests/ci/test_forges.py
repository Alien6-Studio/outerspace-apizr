"""Platform metadata, official schema, original wheel identity and shell parity."""

import hashlib
import json
import os
import re
import runpy
import subprocess
import sys
import zipfile
from pathlib import Path

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = runpy.run_path(str(ROOT / ".github/actions/forge/run.py"))
ACTION = yaml.safe_load((ROOT / "action.yml").read_text())
HEADER, BODY = yaml.safe_load_all((ROOT / "templates/apizr.yml").read_text())
INPUTS = HEADER["spec"]["inputs"]
VALUES = {k: v["default"] for k, v in INPUTS.items()}
SENTINEL = "space 'quote\"; $(touch INJECTED) `touch INJECTED`\nnext"


def interpolate(node, values):
    if isinstance(node, str):

        def replacement(match):
            value = values[match[1]]
            return str(value).lower() if isinstance(value, bool) else value

        return re.sub(r"\$\[\[ inputs\.([\w-]+) \]\]", replacement, node)
    if isinstance(node, dict):
        return {interpolate(k, values): interpolate(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [interpolate(v, values) for v in node]
    return node


def action_values(**updates):
    values = {key: v["default"] for key, v in ACTION["inputs"].items()}
    values.update(updates)
    return values


def test_platform_contracts_and_immutable_supply_chain():
    assert ACTION["name"] and ACTION["description"]
    assert ACTION["runs"]["using"] == "composite"
    assert set(ACTION["inputs"]) == {
        "operation",
        "project",
        "authorize-analysis",
        "operator-policy",
        "output-dir",
        "python-version",
        "apizr-version",
        "wheel-path",
        "wheel-sha256",
    }
    assert ACTION["inputs"]["authorize-analysis"]["default"] == "false"
    assert set(ACTION["outputs"]) == {"result", "artifacts", "apizr-version", "state"}
    dependencies = [s["uses"] for s in ACTION["runs"]["steps"] if "uses" in s]
    assert dependencies == [
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
    ]
    for step in ACTION["runs"]["steps"]:
        if "run" in step:
            assert step["shell"] == "bash"
            assert "${{" not in step["run"]
    assert set(INPUTS) == {
        "job-name",
        "stage",
        "operation",
        "project",
        "authorize-analysis",
        "operator-policy",
        "output-dir",
        "apizr-version",
        "python-image",
    }
    assert INPUTS["authorize-analysis"]["type"] == "boolean"
    assert INPUTS["authorize-analysis"]["default"] is False
    assert INPUTS["operation"]["options"] == ["check", "build-rest", "build-mcp"]
    assert (
        VALUES["python-image"]
        == "python@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d"
    )
    assert set(BODY) == {"$[[ inputs.job-name ]]"}
    job = next(iter(BODY.values()))
    assert job["artifacts"] == {
        "when": "on_success",
        "expire_in": "7 days",
        "paths": ["$[[ inputs.output-dir ]]/"],
    }
    assert all(v["expand"] is False for v in job["variables"].values())
    assert "include" not in BODY and "before_script" not in job
    script = job["script"][0]
    for forbidden in (
        "$[[",
        "scripts/",
        ".github/",
        "pip install plugins",
        "curl",
        "eval ",
        "source ",
    ):
        assert forbidden not in script
    assert '"outerspace-apizr==$APIZR_VERSION"' in script
    assert "--index-url https://pypi.org/simple" in script
    assert "exec env -i" in script


def test_pinned_official_gitlab_schema_and_input_validation():
    fixture = ROOT / "tests/fixtures/forge"
    raw = (fixture / "gitlab-ci.schema.json").read_bytes()
    origin = json.loads((fixture / "gitlab-schema-origin.json").read_text())
    assert hashlib.sha256(raw).hexdigest() == origin["sha256"]
    assert origin["commit"] in origin["source"]
    schema = json.loads(raw)
    jsonschema.validate(HEADER, schema)
    for operation in INPUTS["operation"]["options"]:
        for authorized in (True, False):
            values = dict(
                VALUES, operation=operation, **{"authorize-analysis": authorized}
            )
            body = interpolate(BODY, values)
            assert len(body) == 1
            jsonschema.validate(body, schema)
    for spec in INPUTS.values():
        if "regex" in spec:
            assert re.fullmatch(spec["regex"], spec["default"])
    for value in (
        ".",
        "..",
        "/tmp",
        ".env",
        ".apizr-ci/../secret",
        "${HOME}",
        SENTINEL,
    ):
        assert not re.fullmatch(INPUTS["output-dir"]["regex"], value)
    for value in ("pages", "default", ".hidden", "apizr-" + "a" * 57, SENTINEL):
        assert not re.fullmatch(INPUTS["job-name"]["regex"], value)
    for value in ("latest", ">=0.4.2", "0.4.2;pwd", "0.4.2\n"):
        assert not re.fullmatch(INPUTS["apizr-version"]["regex"], value)


@pytest.mark.parametrize("operation", ["check", "build-rest", "build-mcp"])
@pytest.mark.parametrize("authorized", [True, False])
@pytest.mark.parametrize("project", ["apizr.toml", SENTINEL])
def test_actual_gitlab_shell_argv_equals_action_and_never_executes_input(
    tmp_path, operation, authorized, project
):
    values = dict(
        VALUES,
        operation=operation,
        project=project,
        **{
            "authorize-analysis": authorized,
            "operator-policy": "" if authorized else SENTINEL,
        },
    )
    job = next(iter(interpolate(BODY, values).values()))
    script = job["script"][0]
    assert subprocess.run(["sh", "-n"], input=script, text=True).returncode == 0
    # Exercise the exact component shell argv construction, replacing only the
    # installer/executor with a recorder. No hosted GitLab execution is claimed.
    start = script.index('case "$APIZR_OPERATION"')
    end = script.index("apizr_environment=")
    recorder = tmp_path / "record.py"
    recorder.write_text("import json,sys; print(json.dumps(sys.argv[1:]))")
    command = script[start:end] + '\nexec "$PROOF_PYTHON" "$PROOF_RECORDER" "$@"\n'
    env = {
        "PATH": os.environ["PATH"],
        "PROOF_PYTHON": sys.executable,
        "PROOF_RECORDER": str(recorder),
    }
    env.update({key: item["value"] for key, item in job["variables"].items()})
    process = subprocess.run(
        ["sh", "-eu"],
        input=command,
        text=True,
        env=env,
        cwd=tmp_path,
        capture_output=True,
    )
    assert process.returncode == 0, process.stderr
    expected = ADAPTER["invocation"](
        action_values(
            operation=operation,
            project=project,
            **{
                "authorize-analysis": str(authorized).lower(),
                "operator-policy": values["operator-policy"],
            },
        )
    )
    assert json.loads(process.stdout) == expected
    assert not (tmp_path / "INJECTED").exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"operation": "delivery"},
        {"authorize-analysis": "false"},
        {"authorize-analysis": "TRUE"},
        {"operator-policy": "policy.json"},
        {"apizr-version": "latest"},
        {"output-dir": "../secrets"},
        {"output-dir": SENTINEL},
        {"project": "a\0b"},
    ],
)
def test_action_refuses_invalid_inputs_before_install_or_analysis(changes):
    values = action_values(**{"authorize-analysis": "true"})
    values.update(changes)
    with pytest.raises(ValueError):
        ADAPTER["invocation"](values)


@pytest.mark.parametrize(
    "version, expected",
    [("3.11", 0), ("3.12", 0), ("3.13", 0), ("3.14", 0), ("3.10", 2), (SENTINEL, 2)],
)
def test_actual_action_python_preflight(tmp_path, version, expected):
    process = subprocess.run(
        ["bash", "-eu"],
        input=ACTION["runs"]["steps"][0]["run"],
        text=True,
        cwd=tmp_path,
        env={"APIZR_PYTHON_VERSION": version},
        capture_output=True,
    )
    assert process.returncode == expected
    assert not (tmp_path / "INJECTED").exists()


def wheel(tmp_path, name="outerspace-apizr", version="0.4.2"):
    path = tmp_path / "outerspace_apizr-0.4.2-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "outerspace_apizr-0.4.2.dist-info/METADATA",
            f"Name: {name}\nVersion: {version}\n",
        )
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_original_wheel_identity_and_hash(tmp_path):
    path, digest = wheel(tmp_path)
    name, raw = ADAPTER["wheel_bytes"](str(path), digest, "0.4.2")
    assert name == path.name and raw == path.read_bytes()
    with pytest.raises(ValueError, match="hash_mismatch"):
        ADAPTER["wheel_bytes"](str(path), "0" * 64, "0.4.2")
    for identity in ("other-distribution", "outerspace_apizr"):
        path, digest = wheel(tmp_path, name=identity)
        with pytest.raises(ValueError, match="identity_mismatch"):
            ADAPTER["wheel_bytes"](str(path), digest, "0.4.2")
    path, digest = wheel(tmp_path, version="0.4.1")
    with pytest.raises(ValueError, match="identity_mismatch"):
        ADAPTER["wheel_bytes"](str(path), digest, "0.4.2")
    link = tmp_path / "linked.whl"
    link.symlink_to(path)
    with pytest.raises(OSError):
        ADAPTER["wheel_bytes"](str(link), digest, "0.4.2")
    with pytest.raises(ValueError, match="path_invalid"):
        ADAPTER["wheel_bytes"]("https://example.invalid/file.whl", digest, "0.4.2")


@pytest.mark.parametrize("project_name", ["missing.toml", SENTINEL])
def test_action_missing_checkout_or_project_is_fixed_failure(tmp_path, project_name):
    values = action_values(project=project_name, **{"authorize-analysis": "true"})
    env = {"APIZR_" + k.upper().replace("-", "_"): v for k, v in values.items()}
    env.update(GITHUB_WORKSPACE=str(tmp_path), RUNNER_TEMP=str(tmp_path))
    process = subprocess.run(
        [sys.executable, "-I", str(ROOT / ".github/actions/forge/run.py")],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert process.returncode == 2
    assert process.stderr == "forge_project_missing_checkout_required\n"
    assert not (tmp_path / "INJECTED").exists()


def test_action_install_is_exact_core_only_and_child_has_no_tokens(
    tmp_path, monkeypatch
):
    import types

    values = action_values(**{"authorize-analysis": "true"})
    for key, value in values.items():
        monkeypatch.setenv("APIZR_" + key.upper().replace("-", "_"), value)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "outputs"))
    for key in (
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "CI_JOB_TOKEN",
        "GITLAB_TOKEN",
        "PIP_EXTRA_INDEX_URL",
        "PYTHONPATH",
    ):
        monkeypatch.setenv(key, "SECRET_SENTINEL")
    (tmp_path / "apizr.toml").write_text("placeholder")
    calls = []

    def child(argv, env, quiet=False):
        assert not any("SECRET_SENTINEL" in value for value in env.values())
        calls.append(argv)
        if argv[1:2] == ["ci"]:
            out = tmp_path / ".apizr-ci"
            out.mkdir()
            (out / "result.json").write_text('{"state":"success"}')
        return 0

    # Exercise adapter installation/mapping without fetching unpublished PyPI.
    monkeypatch.setattr(
        ADAPTER["main"].__globals__["venv"].EnvBuilder, "create", lambda *a: None
    )
    monkeypatch.setitem(ADAPTER["main"].__globals__, "child", child)
    monkeypatch.setattr(
        ADAPTER["main"].__globals__["subprocess"],
        "run",
        lambda *a, **kw: types.SimpleNamespace(
            returncode=0, stdout=b"outerspace-apizr 0.4.2\n"
        ),
    )
    assert ADAPTER["main"]() == 0
    assert calls[0][1:] == [
        "-I",
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
        "--index-url",
        "https://pypi.org/simple",
        "outerspace-apizr==0.4.2",
    ]
    assert calls[1][1:] == ADAPTER["invocation"](values)
    assert (
        (tmp_path / "outputs").read_text()
        == "result=.apizr-ci/result.json\nartifacts=.apizr-ci\napizr-version=0.4.2\nstate=success\n"
    )


def test_real_workflow_requires_original_candidate_and_read_only_permissions():
    # BaseLoader avoids interpreting GitHub's `on` as YAML 1.1 boolean.
    workflow = yaml.load(
        (ROOT / ".github/workflows/forge-integrations.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    assert workflow["permissions"] == {"contents": "read"}
    assert {"pull_request", "workflow_dispatch"} <= set(workflow["on"])
    jobs = workflow["jobs"]
    assert all(
        "environment" not in job and "permissions" not in job for job in jobs.values()
    )
    composite = jobs["composite"]
    assert composite["needs"] == "candidate"
    assert composite["strategy"]["matrix"]["python"] == ["3.11", "3.12", "3.13", "3.14"]
    steps = [s for s in composite["steps"] if s.get("uses") == "./"]
    assert {s["with"].get("operation", "check") for s in steps} == {
        "check",
        "build-rest",
        "build-mcp",
    }
    assert any(s.get("continue-on-error") == "true" for s in steps)
    for step in steps:
        assert step["with"]["wheel-path"] == "${{ steps.wheel.outputs.path }}"
        assert step["with"]["wheel-sha256"] == "${{ steps.wheel.outputs.sha256 }}"
    assert (
        "secrets."
        not in (ROOT / ".github/workflows/forge-integrations.yml").read_text()
    )


def test_compact_cross_provider_evidence(tmp_path):
    evidence = []
    for operation in ("check", "build-rest", "build-mcp"):
        values = dict(VALUES, operation=operation, **{"authorize-analysis": True})
        job = next(iter(interpolate(BODY, values).values()))
        script = job["script"][0]
        argv = ADAPTER["invocation"](
            action_values(operation=operation, **{"authorize-analysis": "true"})
        )
        recorder = tmp_path / "record.py"
        recorder.write_text("import json,sys;print(json.dumps(sys.argv[1:]))")
        env = {k: v["value"] for k, v in job["variables"].items()}
        env.update(PROOF_PYTHON=sys.executable, PROOF_RECORDER=str(recorder))
        script = script[
            script.index('case "$APIZR_OPERATION"') : script.index("apizr_environment=")
        ]
        result = subprocess.run(
            ["sh", "-eu"],
            input=script + '\nexec "$PROOF_PYTHON" "$PROOF_RECORDER" "$@"\n',
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        gitlab = json.loads(result.stdout)
        assert argv == gitlab
        evidence.append(
            {
                "github": ["apizr", *argv],
                "gitlab": ["apizr", *gitlab],
                "apizr_version": VALUES["apizr-version"],
            }
        )
    destination = Path(
        os.environ.get("APIZR_FORGE_PARITY_EVIDENCE", str(tmp_path / "parity.json"))
    )
    destination.write_text(
        json.dumps(
            {
                "schema": "apizr.forge-parity/v1",
                "invocations": evidence,
                "gitlab_runtime": "not executed — no GitLab component project authorized",
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
