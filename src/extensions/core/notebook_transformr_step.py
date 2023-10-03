from pathlib import Path
from extensions.step import Step, StepException
from extensions.context import Context

from modules.notebook_transformr.configuration import NotebookTransformrConfiguration
from modules.notebook_transformr.transformr.nbTransformr import NotebookTransformr

class NotebookTransformrStep(Step):
    """
    A step that transforms a notebook using the notebook transformr module
    """

    def __init__(self) -> None:
        super().__init__()


    def execute(self, context: Context):
        """
        Execute the NotebookTransformr step.
        It takes a notebook as input and returns a Python script.
        
        :param context: A dictionary containing data shared across steps.
        """

        # Get context
        self.validate(context)

        configuration: NotebookTransformrConfiguration = context.config
        input_path: Path  = context.input_path # Path to the notebook
        output_dir: Path = context.output_dir

        # Read the code and place it in the context
        context = context.read_input()

        # Convert the notebook into Python code
        try:
            if configuration:
                nb_configuration = configuration
            else:
                if context.prompt:
                    # Prompt the user for configuration
                    self.prompt(context)
                # Use default configuration
                nb_configuration = NotebookTransformrConfiguration()

            # Convert notebook to Python code
            transformr = NotebookTransformr(nb_configuration)
            code, _ = transformr.convert_notebook(context['data'])

            # Place the code in the output
            context.result = code
            context.status = 'success'

            # Save the script
            if output_dir is not None:
                script_name = input_path.stem + ".py"
                context.write_output(script_name)

            return context

        except Exception as e:
            raise StepException(f"Failed to convert {input_path} into Python code.") from e

    def validate(self, context: Context):
        """
        Validate the step.
        
        :param context: A dictionary containing data shared across steps.
        """
        input_path: Path = context.input_path
        
        # Check if input_path is a valid path
        if not input_path.exists():
            raise StepException(f"'{input_path}' does not exist.")
        
        # Check file extension
        if input_path.suffix == ".ipynb":
            # Check if it's a valid notebook
            with input_path.open("r", encoding="utf-8") as f:
                content = f.read()
                if '"cells": [' not in content[:1000]:
                    raise StepException(f"'{input_path}' is not a valid Jupyter notebook.")

    def prompt(context: Context):
        """
        Prompt the user when the configuration has not been provided.
        
        :param context: A dictionary containing data shared across steps.
        """
        pass # No Prompt for now
        