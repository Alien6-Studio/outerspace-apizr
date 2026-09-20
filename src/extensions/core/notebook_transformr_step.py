from ...modules.notebook_transformr.transformr.nbTransformr import NotebookTransformr
from ..context import ContextStatus
from ..step import Step


class NotebookTransformrStep(Step):
    def execute(self, context):
        self.validate(context)
        transformer = NotebookTransformr(context.config)
        source, _ = transformer.convert_notebook(context.input_path)
        from pathlib import Path

        context.input_path = Path(
            transformer.save_script(source, context.output_dir, context.input_path.name)
        )
        context.status = ContextStatus.SUCCESS
        return context
