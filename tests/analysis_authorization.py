"""Exact test-owned grants for existing compiler/CLI regression scenarios.

These helpers supply real policy objects/files; they never patch the admission gate.
Authorization refusal tests call the public APIs directly without these helpers.
"""

import json
import os
import tempfile
from pathlib import Path

from apizr.git_source.models import GitSnapshot
from apizr.operator_policy import OperatorPolicy


def analysis_policy(source):
    if isinstance(source, GitSnapshot):
        target = {
            "kind": "git",
            "repository": source.repository,
            "reference": source.requested_ref,
            "subdir": source.subdir,
        }
    else:
        target = {"kind": "local", "root": os.path.abspath(source)}
    return OperatorPolicy.model_validate_json(
        json.dumps(
            {
                "schema": "apizr.operator-policy/v1",
                "grants": [
                    {
                        "adapter": "repository",
                        "operation": "analyze",
                        "target": target,
                        "permissions": ["source.analyze"],
                    }
                ],
            }
        )
    )


def authorized_main(argv):
    from apizr.cli import main
    from apizr.project import load_project

    args = list(argv)
    if (
        not args
        or args[0] not in {"scan", "graph", "readiness", "expose"}
        or "--git" in args
        or "--operator-policy" in args
        or "--help" in args
    ):
        return main(args)
    index = 3 if args[:2] == ["expose", "build"] else 2 if args[0] == "expose" else 1
    values = args[index:]
    switches = {"--report", "--catalog", "--graph", "--plan", "--details"}
    source = None
    i = 0
    while i < len(values):
        if values[i] in switches:
            i += 1
        elif values[i].startswith("--"):
            i += 2
        else:
            source = values[i]
            break
    if source is None and "--project" in args:
        try:
            source = load_project(Path(args[args.index("--project") + 1])).root
        except (ValueError, OSError):
            return main(args)
    if source is None:
        return main(args)
    with tempfile.TemporaryDirectory(prefix="apizr-test-authority-") as directory:
        policy = Path(directory) / "operator.json"
        policy.write_text(analysis_policy(source).model_dump_json())
        return main([*args, "--operator-policy", str(policy)])
