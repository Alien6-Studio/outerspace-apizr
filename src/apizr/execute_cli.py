"""Explicit experimental execution; inspection and generation never call this."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from apizr.capabilities import document_digest
from apizr.execution import (
    ExecutionPolicy,
    ExecutionResult,
    PolicyRefused,
    execute,
    plan,
)
from apizr.execution.protocol import finite_json
from apizr.inspection import Inspection, inspect_source
from apizr.interfaces.planner import GenerationRefused
from apizr.readiness import assess, report_digest


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="apizr execute",
        description="EXPERIMENTAL: executes TRUSTED source in a fresh local process. Not a filesystem/network sandbox.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("capability", help="One capability name or full ID")
    parser.add_argument("--arguments", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--module-name")
    args = parser.parse_args(argv)
    try:
        with args.policy.open("rb") as file:
            raw_policy = file.read(1048577)
        if len(raw_policy) > 1048576:
            raise ValueError("policy_limit")
        policy = ExecutionPolicy.model_validate_json(raw_policy)
        with args.arguments.open("rb") as file:
            raw_arguments = file.read(policy.limits.max_input_bytes + 1)
        if len(raw_arguments) > policy.limits.max_input_bytes:
            raise ValueError("input_limit")
        payload = finite_json(json.loads(raw_arguments))
        raw = args.source.read_bytes()
        module = args.module_name or args.source.stem
        if args.source.suffix == ".py":
            inspected = inspect_source(raw, module_name=module)
            executable = raw
        elif args.source.suffix == ".ipynb":
            from apizr.capability_notebooks import inspect_notebook_bytes

            notebook = inspect_notebook_bytes(raw, module_name=module)
            executable = notebook.python_source.encode("utf-8")
            readiness = assess(notebook.document, executable)
            inspected = Inspection(
                capability_ir=notebook.document,
                ir_digest=document_digest(notebook.document),
                readiness=readiness,
                readiness_digest=report_digest(readiness),
            )
        else:
            raise ValueError("source_type")
        runtime = plan(inspected, raw, args.capability, policy, executable=executable)
        result = execute(runtime, raw, payload, executable=executable)
    except (PolicyRefused, GenerationRefused):
        result = ExecutionResult(status="policy_refused")
    except (OSError, ValueError, SyntaxError, RecursionError):
        result = ExecutionResult(status="invalid_input")
    print(result.model_dump_json())
    return 0 if result.status == "success" else 1
