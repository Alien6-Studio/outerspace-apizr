import json
from pathlib import Path

import pytest

from apizr.execute_cli import main
from apizr.execution import ExecutionPolicy, plan, plan_bytes, policy_bytes
from apizr.inspection import inspect_source

pytestmark = pytest.mark.timeout(20)


@pytest.mark.parametrize("kind", ["py", "ipynb"])
def test_explicit_execution_cli(tmp_path, capsys, kind):
    source = "def total(values: list[int]) -> int: return sum(values)\n"
    if kind == "ipynb":
        source = json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": "sample",
                        "metadata": {},
                        "execution_count": None,
                        "outputs": [],
                        "source": source,
                    }
                ],
            }
        )
    target = tmp_path / ("sample." + kind)
    target.write_text(source)
    args = tmp_path / "arguments.json"
    args.write_text('{"values":[1,2]}')
    policy = tmp_path / "policy.json"
    policy.write_text("{}")
    command = [
        str(target),
        "total",
        "--arguments",
        str(args),
        "--policy",
        str(policy),
        "--module-name",
        "cli.sample",
    ]
    assert main(command) == 0
    assert json.loads(capsys.readouterr().out)["value"] == 3
    policy.write_text('{"network":{"mode":"deny"}}')
    assert main(command) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "policy_refused"
    policy.write_text("{}")
    command[1] = "missing"
    assert main(command) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "invalid_input"
    args.write_text('{"values":[null]}')
    command[1] = "total"
    assert main(command) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "invalid_input"


def test_cli_refuses_oversized_or_invalid_files(tmp_path, capsys):
    source, args, policy = [
        tmp_path / name for name in ["source.txt", "args.json", "policy.json"]
    ]
    source.write_text("private invalid source")
    args.write_text("{}")
    policy.write_text("{}")
    command = [str(source), "f", "--arguments", str(args), "--policy", str(policy)]
    for changed, content in [
        (source, "unsupported suffix"),
        (policy, "{}" + " " * 1048576),
        (policy, "not JSON"),
        (policy, "{}"),
        (args, " " * 1048577),
    ]:
        changed.write_text(content)
        assert main(command) == 1
        assert json.loads(capsys.readouterr().out)["status"] == "invalid_input"


def test_policy_plan_golden_across_supported_python():
    root = Path(__file__).parents[1] / "fixtures" / "execution"
    source = (root / "source.py").read_bytes()
    policy = ExecutionPolicy()
    runtime = plan(
        inspect_source(source, module_name="golden.execution"), source, "add", policy
    )
    assert policy_bytes(policy) == (root / "policy.json").read_bytes()
    assert plan_bytes(runtime) == (root / "plan.json").read_bytes()
