"""Static and runtime commands, separate from the historical generation parser."""

import sys
from importlib.metadata import version
from typing import Sequence

from apizr.environment.extras import MissingExtra, available, require


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return _main(argv)
    except MissingExtra as error:
        print(f"apizr: {error}", file=sys.stderr)
        return 2


def _main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["--version"]:
        print(f"outerspace-apizr {version('outerspace-apizr')}")
        return 0
    if arguments and arguments[0] == "ci":
        from apizr.cli.commands.ci import main as ci_command

        return ci_command(arguments[1:])
    if arguments and arguments[0] in ("completion", "__complete"):
        from apizr.cli.completion import main as completion_command

        return completion_command(arguments[1:], backend=arguments[0] == "__complete")
    if arguments and arguments[0] in ("init", "doctor"):
        from apizr.cli.commands.onboarding import diagnose, init

        return (init if arguments[0] == "init" else diagnose)(arguments[1:])
    if arguments and arguments[0] == "clients":
        from apizr.cli.commands.clients import main as clients_command

        return clients_command(arguments[1:])
    if arguments and arguments[0] == "delivery":
        from apizr.cli.commands.delivery import main as delivery_command

        return delivery_command(arguments[1:])
    if arguments and arguments[0] == "mcp":
        from apizr.cli.commands.mcp import main as mcp_command

        return mcp_command(arguments[1:])
    if arguments and arguments[0] == "plugins":
        from apizr.cli.commands.plugins import main as plugins_command

        return plugins_command(arguments[1:])
    if arguments and arguments[0] == "expose":
        from apizr.cli.commands.exposure import main as exposure_command

        return exposure_command(arguments[1:])
    if arguments and arguments[0] == "readiness":
        from apizr.cli.commands.readiness import main as readiness_repo_command

        return readiness_repo_command(arguments[1:])
    if arguments and arguments[0] == "repository-readiness":
        from apizr.cli.commands.repository_readiness import main as readiness_command

        return readiness_command(arguments[1:])
    if arguments and arguments[0] == "graph":
        from apizr.cli.commands.graph import main as graph_command

        return graph_command(arguments[1:])
    if arguments and arguments[0] == "scan":
        from apizr.cli.commands.scan import main as scan_command

        return scan_command(arguments[1:])
    if arguments and arguments[0] == "execute":
        from apizr.cli.commands.execute import main as execute_command

        return execute_command(arguments[1:])
    if arguments and arguments[0] == "inspect":
        from apizr.cli.commands.inspect import main as inspect_command

        return inspect_command(arguments[1:])
    if arguments and arguments[0] == "experiment":
        from apizr.cli.commands.experiment import main as experiment_command

        return experiment_command(arguments[1:])
    if arguments and arguments[0] == "generate":
        from apizr.cli.commands.generate import main as generate_modern

        return generate_modern(arguments[1:])
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
        print(
            "Extensions: apizr plugins {install,list,enable,disable,run,uninstall} --help"
        )
        print("Project plugins: apizr plugins {lock,sync,update,catalog} --help")
        print("Delivery of an existing build: apizr delivery {run,resume} --help")
        print("\nData science: apizr experiment inspect SOURCE [--format json]")
        print("  Understand script/notebook evidence without executing code.")
        print("  apizr experiment run SOURCE — execute trusted code with host access.")
        print("  apizr experiment list | apizr experiment show RUN — local history.")
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
    require(
        "legacy", "yaml", "questionary", "jinja2", "packaging", "nbconvert", "black"
    )
    from apizr.legacy.main import main as generate

    generate(arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
