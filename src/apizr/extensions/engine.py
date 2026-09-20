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

    def add_step(self, step_name, context):
        if step_name not in STEPS:
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
            result = STEPS[name]().execute(context)
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
