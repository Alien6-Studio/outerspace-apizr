"""Command-line entry point for the complete conversion pipeline."""

import argparse
import json
from pathlib import Path

import yaml

from apizr.modules.code_analyzr.analyzr.ast_node.astNodeException import (
    AnnotationException,
)
from apizr.runtime import parse_python_target, python_target_argument

from .configuration import MainConfiguration
from .extensions.context import Context
from .extensions.engine import AutomationEngine
from .extensions.plugins.api import load_plugins
from .legacy_delivery import (
    build_image,
    copy_resources,
    resource_files,
    validate_image_tag,
)


def handle_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate a FastAPI project from a Python script or Jupyter notebook."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--notebook", type=Path)
    source.add_argument("--script", type=Path)
    parser.add_argument("--configuration", type=Path)
    parser.add_argument(
        "--plugin",
        action="append",
        default=[],
        metavar="NAME",
        help="Explicitly load a trusted installed apizr.pipeline.v1 extension (repeatable)",
    )
    parser.add_argument(
        "--python-version",
        type=python_target_argument,
        metavar="3.11–3.14",
        help="Target Python version; defaults to the running interpreter",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="PATH",
        help="Include a data/config file or directory relative to the source directory (repeatable)",
    )
    parser.add_argument(
        "--build-image",
        metavar="TAG",
        help="After generation, explicitly run a local Docker build; does not start or publish the image",
    )
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
    configuration = MainConfiguration()
    if args.configuration:
        data = yaml.safe_load(args.configuration.read_text(encoding="utf-8")) or {}
        configuration = MainConfiguration.model_validate(data)
    elif args.interactive:
        from .prompt import ConfigPrompter

        configuration = ConfigPrompter(args.lang).getConfiguration()
    if args.python_version:
        configuration.python_version = parse_python_target(args.python_version)
    configuration.dispatch()
    context.config = configuration
    context.input_path = (args.notebook or args.script).resolve()
    assert isinstance(context.input_path, Path)
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
        args.requirements.resolve()
        if args.requirements
        else (context.input_path.parent / configuration.requirements).resolve()
        if configuration.requirements is not None
        else None
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
            not args.skip_pipreqs or context.requirements_path is not None,
            "dockerizr",
        ),
        ("DockerizrStep", not args.skip_docker, "dockerizr"),
    ]
    plugins = load_plugins(args.plugin)
    enabled_names = {name for name, enabled, _ in steps if enabled}
    for name, plugin in plugins:
        if plugin.after not in enabled_names:
            raise ValueError(
                f"Pipeline plugin {name!r} requires enabled step {plugin.after!r}"
            )
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
            for plugin_name, plugin in plugins:
                if plugin.after == name:
                    extension = Context()
                    extension.config = context.config
                    extension.input_path = context.input_path
                    extension.source_dir = context.input_path.parent
                    extension.output_dir = context.output_dir
                    extension.options = context.config.plugin_options.get(
                        plugin_name, {}
                    ).copy()
                    engine.add_plugin(plugin_name, plugin, extension)
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
    plugins=None,
    include=None,
    image_tag=None,
):
    """Generate files; plugins and Docker builds run only when explicitly requested."""
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
        plugin=list(plugins or ()),
        include=list(include or ()),
        build_image=image_tag,
    )
    return run_pipeline(args)


def run_pipeline(args):
    if args.build_image is not None:
        validate_image_tag(args.build_image)
        if args.skip_docker:
            raise ValueError("--build-image cannot be combined with --skip-docker")
    source_dir = (args.notebook or args.script).resolve().parent
    context = init_context(args)
    assert isinstance(context.config, MainConfiguration)
    included = args.include or context.config.include
    files = resource_files(source_dir, included)
    assert isinstance(context.output_dir, Path)
    if any(context.output_dir.is_relative_to(source_dir / name) for name in included):
        raise ValueError("Output directory must not be inside included resources")
    result = init_engine(args, context).run()
    copy_resources(files, context.output_dir)
    result["files"] = sorted(
        str(p.relative_to(context.output_dir))
        for p in context.output_dir.rglob("*")
        if p.is_file()
    )
    if args.build_image is not None:
        result["image"] = {
            "tag": args.build_image,
            "id": build_image(context.output_dir, args.build_image),
        }
    return result


def main(argv=None):
    args = handle_args(argv)
    try:
        result = run_pipeline(args)
    except (ValueError, OSError, RuntimeError, SyntaxError, AnnotationException) as exc:
        raise SystemExit(f"apizr: {exc}") from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
