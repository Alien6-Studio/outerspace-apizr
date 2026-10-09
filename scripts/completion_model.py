"""Development-only parser snapshot; tests fail on any modern CLI grammar drift."""

import argparse
import importlib
import json
from pathlib import Path
from unittest.mock import patch

ENTRYPOINTS = {
    "inspect": ("apizr.cli.commands.inspect", "main"),
    **{
        name: (f"apizr.cli.commands.{name.replace('-', '_')}", "main")
        for name in (
            "scan",
            "ci",
            "graph",
            "readiness",
            "repository-readiness",
            "expose",
            "execute",
            "generate",
            "clients",
            "delivery",
            "mcp",
            "plugins",
        )
    },
    "init": ("apizr.cli.commands.onboarding", "init"),
    "doctor": ("apizr.cli.commands.onboarding", "diagnose"),
    "completion": ("apizr.cli.completion", "main"),
}
ENTRYPOINTS["expose"] = ("apizr.cli.commands.exposure", "main")
PATH_NAMES = {"source_root", "exclude_dir"}


def describe(parser: argparse.ArgumentParser) -> dict:
    result = {"options": {}, "arguments": [], "commands": {}}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            result["commands"] = {
                name: describe(child) for name, child in action.choices.items()
            }
            continue
        info = {
            "value": action.nargs != 0,
            "choices": [str(v) for v in (action.choices or ())],
            "path": action.type is Path or action.dest in PATH_NAMES,
            "nargs": action.nargs,
        }
        if action.option_strings:
            for option in action.option_strings:
                result["options"][option] = info
        else:
            result["arguments"].append(info)
    return result


def capture() -> dict:
    class Captured(BaseException):
        pass

    result = {
        "options": {
            name: {"value": False, "choices": [], "path": False, "nargs": 0}
            for name in ("--help", "-h", "--version")
        },
        "arguments": [],
        "commands": {},
    }
    for name, (module, function) in ENTRYPOINTS.items():
        saved = []

        def stop(parser, *args, _saved=saved, **kwargs):
            _saved.append(describe(parser))
            raise Captured()

        with patch.object(argparse.ArgumentParser, "parse_args", stop):
            try:
                getattr(importlib.import_module(module), function)([])
            except Captured:
                pass
        assert len(saved) == 1, name
        result["commands"][name] = saved[0]
    return result


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "src/apizr/cli/completion_spec.py"
    target.write_text(
        '"""Static modern CLI grammar. Regenerate with scripts/completion_model.py."""\n\nimport json\n\nCOMMANDS = json.loads(\n    r\'\'\''
        + json.dumps(capture(), sort_keys=True, separators=(",", ":"))
        + "'''\n)\n"
    )
