import keyword
from pathlib import Path

from ...modules.fast_apizr.generator.analyzr import Analyzr
from ...modules.fast_apizr.generator.fastApiAppGenerator import FastApiAppGenerator
from ..context import ContextStatus
from ..step import Step


class FastApizrStep(Step):
    def execute(self, context):
        self.validate(context)
        config = context.config.model_copy(deep=True)
        config.module_name = context.input_path.stem
        filename = (
            config.api_filename
            if "api_filename" in config.model_fields_set
            else f"{config.module_name}_api.py"
        )
        if (
            Path(filename).name != filename
            or not filename.endswith(".py")
            or not Path(filename).stem.isidentifier()
            or keyword.iskeyword(Path(filename).stem)
        ):
            raise ValueError(
                "api_filename must be a Python filename without directory components"
            )
        if (context.output_dir / filename).exists():
            raise ValueError(
                f"Generated API would overwrite an existing module: {filename}"
            )
        content = Analyzr.model_validate_json(context.data["CodeAnalyzr"])
        if not any(f.selected for f in content.functions):
            raise ValueError(
                "No functions selected. Define at least one top-level Python function to expose."
            )
        context.result = (
            "FastApizr",
            FastApiAppGenerator(config, content).gen_fastapi_app(),
        )
        context.write_output("FastApizr", filename)
        context.result = ("api_module", Path(filename).stem)
        context.status = ContextStatus.SUCCESS
        return context
