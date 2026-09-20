from pathlib import Path

from extensions.context import Context
from extensions.step import Step, StepException

from modules.dockerizr.configuration import DockerizrConfiguration
from modules.dockerizr.generator.requirementsAnalyzr import RequirementsAnalyzr

class RequirementsAnalyzrStep(Step):
    """
    A step that produces a requirements.txt file from a Python script
    """

    def __init__(self) -> None:
        super().__init__()

    def execute(self, context: Context):
        """
        Execute the RequirementsAnalyzr step.

        :param context: A dictionary containing data shared across steps.
        """

        # Get context
        self.validate(context)

        configuration: DockerizrConfiguration = context.config
        output_dir: Path = context.output_dir
        configuration.project_path = str(output_dir.resolve())
        try:
            RequirementsAnalyzr(configuration).generate_requirements()
            print("Requirements file generated.")
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
        
    def prompt(context: Context):
        """
        Prompt the user when the configuration has not been provided.
        
        :param context: A dictionary containing data shared across steps.
        """
        pass # No Prompt for now