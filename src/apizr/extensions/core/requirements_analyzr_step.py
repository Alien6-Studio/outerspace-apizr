from ...modules.dockerizr.generator.requirementsAnalyzr import RequirementsAnalyzr
from ..context import ContextStatus
from ..step import Step


class RequirementsAnalyzrStep(Step):
    def execute(self, context):
        config = context.config.model_copy(deep=True)
        config.project_path = str(context.output_dir)
        RequirementsAnalyzr(config).generate_requirements(context.requirements_path)
        context.status = ContextStatus.SUCCESS
        return context
