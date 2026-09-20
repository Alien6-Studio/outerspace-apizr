"""Command-line entry point for the complete conversion pipeline."""

import argparse
import json
from pathlib import Path

import yaml

from .configuration import MainConfiguration
from .extensions.context import Context
from .extensions.engine import AutomationEngine


def handle_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate a FastAPI project from a Python script or Jupyter notebook."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--notebook", type=Path)
    source.add_argument("--script", type=Path)
    parser.add_argument("--configuration", type=Path)
    parser.add_argument(
        "--python-version",
        choices=["3.{}".format(minor) for minor in range(8, 15)],
        help="Target Python version; defaults to the running interpreter",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--requirements",
        type=Path,
        help="Use an explicit requirements.txt instead of import inference",
    )
    parser.add_argument("--skip-fastapi", action="store_true")
    parser.add_argument("--skip-docker", action="store_true")
    parser.add_argument(
        "--skip-pipreqs",
        action="store_true",
        help="Skip dependency inference; an explicit requirements file can still be supplied",
    )
    parser.add_argument("--lang", choices=["en", "fr"], default="en")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--force",
        action="store_true",
        help="Use non-interactive defaults (also the default behavior)",
    )
    mode.add_argument("--interactive", action="store_true")
    return parser.parse_args(argv)


def init_context(args):
    context = Context()
    context.config = MainConfiguration()
    if args.configuration:
        data = yaml.safe_load(args.configuration.read_text(encoding="utf-8")) or {}
        context.config = MainConfiguration.model_validate(data)
    elif args.interactive:
        from .prompt import ConfigPrompter

        context.config = ConfigPrompter(args.lang).getConfiguration()
    if args.python_version:
        context.config.python_version = tuple(map(int, args.python_version.split(".")))
    context.config.dispatch()
    context.input_path = (args.notebook or args.script).resolve()
    if not context.input_path.is_file():
        raise ValueError(f"Input file does not exist: {context.input_path}")
    expected = ".ipynb" if args.notebook else ".py"
    if context.input_path.suffix != expected:
        raise ValueError(f"Expected a {expected} input file")
    context.output_dir = (
        args.output_dir or Path(".output") / context.input_path.stem
    ).resolve()
    if context.output_dir == context.input_path.parent:
        raise ValueError("Output must be a separate directory from the source")
    # Existing outputs may contain stale modules or user files; never silently overwrite them.
    if context.output_dir.exists() and any(context.output_dir.iterdir()):
        raise ValueError(f"Output directory is not empty: {context.output_dir}")
    context.output_dir.mkdir(parents=True, exist_ok=True)
    context.lang = args.lang
    context.prompt = False
    context.requirements_path = (
        args.requirements.resolve() if args.requirements else None
    )
    return context


def init_engine(args, context):
    if args.skip_fastapi and not args.skip_docker:
        raise ValueError("--skip-fastapi requires --skip-docker")
    engine = AutomationEngine()
    steps = [
        ("NotebookTransformrStep", args.notebook is not None, "notebook_transformr"),
        ("CodeAnalyzrStep", True, "code_analyzr"),
        ("FastApizrStep", not args.skip_fastapi, "fast_apizr"),
        (
            "RequirementsAnalyzrStep",
            not args.skip_pipreqs or args.requirements is not None,
            "dockerizr",
        ),
        ("DockerizrStep", not args.skip_docker, "dockerizr"),
    ]
    for name, enabled, key in steps:
        if enabled:
            step = Context()
            step.config = getattr(context.config, key)
            step.input_path = context.input_path
            step.source_dir = context.input_path.parent
            step.output_dir = context.output_dir
            step.prompt = False
            step.requirements_path = context.requirements_path
            engine.add_step(name, step)
    return engine


def convert(
    input_path,
    output_dir,
    *,
    configuration=None,
    python_version=None,
    requirements=None,
    skip_docker=False,
    skip_fastapi=False,
    skip_pipreqs=False,
):
    """Generate files without importing or executing the user's Python code."""
    path = Path(input_path)
    args = argparse.Namespace(
        notebook=path if path.suffix == ".ipynb" else None,
        script=path if path.suffix != ".ipynb" else None,
        output_dir=Path(output_dir),
        configuration=Path(configuration) if configuration else None,
        python_version=python_version,
        requirements=Path(requirements) if requirements else None,
        skip_docker=skip_docker,
        skip_fastapi=skip_fastapi,
        skip_pipreqs=skip_pipreqs,
        force=True,
        interactive=False,
        lang="en",
    )
    context = init_context(args)
    return init_engine(args, context).run()


def main(argv=None):
    args = handle_args(argv)
    try:
        result = init_engine(args, init_context(args)).run()
    except (ValueError, OSError, RuntimeError, SyntaxError) as exc:
        raise SystemExit(f"apizr: {exc}") from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
