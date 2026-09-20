"""Modern generation orchestration; analysis stays upstream of REST planning."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="apizr generate")
    targets = parser.add_subparsers(dest="target", required=True)
    rest = targets.add_parser("rest", help="Generate a static REST/OpenAPI bundle")
    rest.add_argument("source", type=Path)
    rest.add_argument("--output-dir", type=Path, required=True)
    rest.add_argument("--module-name")
    rest.add_argument("--select", help="Comma-separated capability names or IDs")
    args = parser.parse_args(argv)
    from apizr.capabilities import document_digest
    from apizr.generators.rest import generate
    from apizr.generators.rest.planner import GenerationRefused
    from apizr.generators.rest.schema import ContractError
    from apizr.inspection import Inspection, inspect_source
    from apizr.readiness import assess, report_digest

    try:
        module_name = args.module_name or args.source.stem
        if args.source.suffix not in {".py", ".ipynb"}:
            raise ValueError("REST generation supports one .py or .ipynb file")
        raw = args.source.read_bytes()
        executable = raw
        if args.source.suffix == ".py":
            inspected = inspect_source(raw, module_name=module_name)
        else:
            from apizr.capability_notebooks import inspect_notebook_bytes

            notebook = inspect_notebook_bytes(raw, module_name=module_name)
            executable = notebook.python_source.encode("utf-8")
            readiness = assess(notebook.document, executable)
            inspected = Inspection(
                capability_ir=notebook.document,
                ir_digest=document_digest(notebook.document),
                readiness=readiness,
                readiness_digest=report_digest(readiness),
            )
        selected = None
        if args.select is not None:
            selected = [part.strip() for part in args.select.split(",")]
            if not all(selected):
                raise ValueError("Selection requires non-empty capability names or IDs")
        names = generate(
            inspected, raw, args.output_dir, executable=executable, select=selected
        )
    except (GenerationRefused, ContractError) as error:
        print(f"apizr generate rest: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError, SyntaxError, UnicodeError, RecursionError) as error:
        message = error.msg if isinstance(error, SyntaxError) else str(error)
        print(f"apizr generate rest: {message}", file=sys.stderr)
        return 2
    print(
        json.dumps({"schema_version": "apizr.rest/v1", "files": names}, sort_keys=True)
    )
    return 0
