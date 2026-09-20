from pathlib import Path

from extensions.context import Context
from extensions.step import Step, StepException

from modules.dockerizr.configuration import DockerizrConfiguration
from modules.dockerizr.generator.dockerfileGenerator import DockerfileGenerator
from modules.dockerizr.generator.gunicornGenerator import GunicornGenerator
from modules.dockerizr.prompt import ConfigPrompter

class DockerizrStep(Step):
    """
    A step that transforms a notebook using the notebook transformr module
    """

    def __init__(self) -> None:
        super().__init__()

    def execute(self, context):
        """
        Execute the step.
        
        :param context: A dictionary containing data shared across steps.
        """

        # Get context
        self.validate(context)

        configuration: DockerizrConfiguration = context.config
        input_path: Path  = context.input_path
        output_dir: Path = context.output_dir

        script_name = input_path.stem + ".py"

        try:
            # Case 1 Prompt the user for configuration
            if context.prompt:
                context.config.api_filename = script_name.replace(".py", "_api.py")
                context.config.project_path = str(output_dir.resolve())
                dockerizr_configuration = self.prompt(context).config
            # Case 2 : Use the configuration w/o prompting when requested
            elif configuration:
                dockerizr_configuration = configuration
            # Otherwise: Use default configuration
            else:
                # Set the project path to the absolute path of the output directory
                dockerizr_configuration: DockerizrConfiguration = DockerizrConfiguration()
                dockerizr_configuration.api_filename = script_name.replace(".py", "_api.py")
                dockerizr_configuration.project_path = str(output_dir.resolve())

            # Generate necessary files for dockerization
            GunicornGenerator(dockerizr_configuration).generate_gunicorn()
            DockerfileGenerator(dockerizr_configuration).generate_dockerfile()

            context.status = 'success'
            return context

        except Exception as e:
            context.add_log(message = f"Error during dockerization process: {str(e)}", level="error")
            raise StepException(f"Failed during dockerization process: {str(e)}") from e

    def validate(self, context: Context):
        """
        Validate the context.
        """
        input_path: Path = context.input_path
        
        # Check if input_path is a valid path
        if not input_path.exists():
            raise StepException(f"'{input_path}' does not exist.")

    def prompt(self, context: Context):
        """
        Prompt the user for configuration.
        """
        _config:  DockerizrConfiguration = context.config
        context.config = ConfigPrompter(
            lang=context.lang).getConfiguration(
                version=_config.python_version,
                encoding=_config.encoding,
                api_filename=_config.api_filename,
                module_name=_config.module_name,
                project_path=_config.project_path,
            )
        return context