from pathlib import Path

from .context import Context
from .core import (
    CodeAnalyzrStep,
    DockerizrStep,
    FastApizrStep,
    NotebookTransformrStep,
    RequirementsAnalyzrStep,
)

STEPS = {
    cls.__name__: cls
    for cls in (
        NotebookTransformrStep,
        CodeAnalyzrStep,
        FastApizrStep,
        RequirementsAnalyzrStep,
        DockerizrStep,
    )
}


class AutomationEngine:
    def __init__(self):
        self.steps = []
        self.registry = dict(STEPS)

    def add_plugin(self, name, plugin, context):
        key = "plugin:" + name
        if key in self.registry:
            raise ValueError(f"Duplicate pipeline plugin: {name}")
        self.registry[key] = plugin
        self.steps.append((key, context))

    def add_step(self, step_name, context):
        if step_name not in self.registry:
            raise ValueError(f"Unknown step: {step_name}")
        self.steps.append((step_name, context))

    def run(self):
        shared = {}
        current_input = None
        output_dir = None
        for name, context in self.steps:
            context.data = shared.copy()
            if current_input is not None:
                context.input_path = current_input
            expected_output = context.output_dir
            expected_input = context.input_path
            try:
                result = self.registry[name]().execute(context)
            except Exception as exc:
                if name.startswith("plugin:"):
                    raise RuntimeError(f"Pipeline {name} failed") from exc
                raise
            if name.startswith("plugin:"):
                if (
                    not isinstance(result, Context)
                    or result.output_dir != expected_output
                ):
                    raise ValueError(
                        f"Pipeline {name} must return a Context with the same output directory"
                    )
                if result.input_path != expected_input and (
                    not isinstance(result.input_path, Path)
                    or not result.input_path.is_file()
                    or not result.input_path.resolve().is_relative_to(
                        expected_output.resolve()
                    )
                ):
                    raise ValueError(f"Pipeline {name} returned an invalid input path")
            shared.update(result.result)
            current_input = result.input_path
            output_dir = result.output_dir
        return {
            "output_dir": str(output_dir) if output_dir else None,
            "api_module": shared.get("api_module"),
            "files": sorted(
                str(p.relative_to(output_dir))
                for p in output_dir.rglob("*")
                if p.is_file()
            )
            if output_dir
            else [],
        }
