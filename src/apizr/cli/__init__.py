"""Static and runtime commands, separate from the historical generation parser."""

import sys
from functools import partial
from importlib import import_module
from importlib.metadata import version
from typing import Sequence

from apizr.environment.extras import MissingExtra, available, require

# Only the selected adapter is imported. Completion and onboarding have distinct
# call signatures and remain explicit in _main alongside the top-level help.
COMMAND_TARGETS: dict[str, tuple[str, str]] = {
    "telemetry": ("apizr.cli.commands.telemetry", "main"),
    "editor": ("apizr.cli.commands.editor", "main"),
    "ci": ("apizr.cli.commands.ci", "main"),
    "clients": ("apizr.cli.commands.clients", "main"),
    "delivery": ("apizr.cli.commands.delivery", "main"),
    "mcp": ("apizr.cli.commands.mcp", "main"),
    "plugins": ("apizr.cli.commands.plugins", "main"),
    "expose": ("apizr.cli.commands.exposure", "main"),
    "readiness": ("apizr.cli.commands.readiness", "main"),
    "repository-readiness": ("apizr.cli.commands.repository_readiness", "main"),
    "graph": ("apizr.cli.commands.graph", "main"),
    "scan": ("apizr.cli.commands.scan", "main"),
    "execute": ("apizr.cli.commands.execute", "main"),
    "inspect": ("apizr.cli.commands.inspect", "main"),
    "experiment": ("apizr.cli.commands.experiment", "main"),
    "generate": ("apizr.cli.commands.generate", "main"),
}


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)

    try:
        try:
            from apizr.cli.commands.telemetry import run_command
        except Exception:
            return _main(arguments)
        return run_command(arguments, partial(_main, arguments))
    except MissingExtra as error:
        print(f"apizr: {error}", file=sys.stderr)
        return 2


def _main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--version"]:
        print(f"outerspace-apizr {version('outerspace-apizr')}")
        return 0
    if arguments and arguments[0] in ("completion", "__complete"):
        from apizr.cli.completion import main as completion_command

        return completion_command(arguments[1:], backend=arguments[0] == "__complete")
    if arguments and arguments[0] in ("init", "doctor"):
        from apizr.cli.commands.onboarding import diagnose, init

        return (init if arguments[0] == "init" else diagnose)(arguments[1:])
    if arguments and arguments[0] in COMMAND_TARGETS:
        module, attribute = COMMAND_TARGETS[arguments[0]]
        return getattr(import_module(module), attribute)(arguments[1:])
    # Help describes ordered workflows, permissions and prerequisites rather
    # than a flat command list. Keep its reviewed text byte-stable; completion
    # tests bind COMMAND_TARGETS and the explicit cases to the captured grammar.
    if arguments in (["--help"], ["-h"]):
        print("Apizr — an open-source capability compiler for Python codebases.\n")
        print("Version: apizr --version")
        print(
            "Local setup: apizr init | apizr doctor | apizr completion {bash,zsh,fish}"
        )
        print("Local client collections: apizr clients {export,sync} --help")
        print(
            "Static CI validation/build: apizr ci {check,build-rest,build-mcp} --help"
        )
        print("Local MCP analysis server (optional plugin): apizr mcp serve --help")
        print("Editor JSON request/response: apizr editor --help")
        print(
            "Local telemetry controls: apizr telemetry {status,enable,disable,preview}"
        )
        print(
            "Extensions: apizr plugins {install,list,enable,disable,run,uninstall} --help"
        )
        print("Project plugins: apizr plugins {lock,sync,update,catalog} --help")
        print("Delivery of an existing build: apizr delivery {run,resume} --help")
        print("\nData science: apizr experiment inspect SOURCE [--format json]")
        print("  Understand script/notebook evidence without executing code.")
        print("  apizr experiment run SOURCE — execute trusted code with host access.")
        print("  apizr experiment list | apizr experiment show RUN — local history.")
        print("  apizr experiment diff RUN_A RUN_B — compare recorded evidence.")
        print(
            "  apizr experiment expose RUN --capability ID --interface rest|mcp --output-dir DIR"
        )
        print(
            "  Inspect → Run → Compare → Expose; repository Readiness still decides eligibility."
        )
        print(
            "\nRepository workflow: Discover → Understand → Assess → Select → Expose → Execute"
        )
        print(
            "Repository analysis requires --operator-policy OPERATOR.json (source.analyze)."
        )
        print("Git adds --git URL --ref REF and a separate git.fetch grant.")
        print("Use --project apizr.toml for explicit local project configuration.")
        print("Discover: apizr scan ROOT [--source-root DIR] [--catalog]")
        print("Understand: apizr graph ROOT [--source-root DIR] [--graph]")
        print("Assess: apizr readiness ROOT [--policy READINESS.json] [--report]")
        print("Select: apizr expose plan ROOT --policy EXPOSURE.json [--plan]")
        print(
            "Expose: apizr expose build {rest,mcp} ROOT --policy EXPOSURE.json --output-dir DIR"
        )
        print(
            "  Add --execution-policy EXECUTION.json for fresh local/OCI workers; default: direct."
        )
        print(
            "  READY does not mean exposed. Supporting dependencies are not automatically public."
        )
        print("\nSingle-source workflows (Python or notebook):")
        print("  apizr inspect SOURCE [--format json | --ir] [--module-name NAME]")
        print("  apizr generate {rest,mcp} SOURCE --output-dir DIR [--select NAMES]")
        print("  apizr execute SOURCE CAPABILITY --arguments FILE --policy FILE")
        print(
            "  Execution is trusted-code oriented; local processes are not filesystem/network sandboxes."
        )
        print(
            "Artifact-first readiness: apizr repository-readiness CATALOG GRAPH --policy FILE"
        )
        print("\nLegacy generation pipeline (retained for compatibility):")
        if not available(
            "yaml", "questionary", "jinja2", "packaging", "nbconvert", "black"
        ):
            print("  apizr --script FILE | --notebook FILE --output-dir DIR")
            print(
                "  Install outerspace-apizr[legacy] for legacy generation and its full help."
            )
            return 0
        from apizr.legacy.main import main as generate

        try:
            generate(arguments)
        except SystemExit as exc:
            if exc.code != 0:
                raise
        return 0
    # The remaining historical generation fallback is retired by #284/#331.
    require(
        "legacy", "yaml", "questionary", "jinja2", "packaging", "nbconvert", "black"
    )
    from apizr.legacy.main import main as generate

    generate(arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
