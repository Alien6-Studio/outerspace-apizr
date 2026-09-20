from ...modules.dockerizr.generator.dockerfileGenerator import DockerfileGenerator
from ..context import ContextStatus
from ..step import Step


class DockerizrStep(Step):
    def execute(self, context):
        config = context.config.model_copy(deep=True)
        config.project_path = str(context.output_dir)
        config.module_name = context.data["api_module"]
        config.api_filename = config.module_name + ".py"
        if not (context.output_dir / "requirements.txt").is_file():
            raise ValueError(
                "Docker generation requires requirements.txt; supply --requirements or enable dependency inference"
            )
        DockerfileGenerator(config).generate_dockerfile()
        context.status = ContextStatus.SUCCESS
        return context
