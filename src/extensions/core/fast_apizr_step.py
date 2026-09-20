import json
import os
import shutil

from pathlib import Path
from extensions.context import Context
from extensions.step import Step, StepException

from modules.fast_apizr.configuration import FastApizrConfiguration
from modules.fast_apizr.generator.analyzr import Analyzr as FastApiAnalyzr
from modules.fast_apizr.generator.exceptions import FastApiAlreadyImplementedException
from modules.fast_apizr.generator.fastApiAppGenerator import FastApiAppGenerator
from modules.fast_apizr.prompt import ConfigPrompter

class FastApizrStep(Step):
    """
    A step that transforms a notebook using the notebook transformr module
    """

    def __init__(self) -> None:
        super().__init__()


    def execute(self, context: Context):
        """
        Execute the step.
        
        :param context: A dictionary containing data shared across steps.
        """

        # Get context
        self.validate(context)

        configuration: FastApizrConfiguration = context.config
        input_path: Path  = context.input_path # Path to the script
        output_dir: Path = context.output_dir

        metadata: str = context.data['CodeAnalyzr']
        script_name = input_path.stem + ".py"
        api_filename = os.path.basename(script_name).replace(".py", "_api.py")

        try:
            # Case 1 Prompt the user for configuration
            if context.prompt:
                # use default for context.config.api_filename since it is not used
                # use default for context.config.module_name
                fast_apizr_configuration = self.prompt(context).config
            # Case 2 : Use the configuration w/o prompting when requested
            elif context.config:
                fast_apizr_configuration = configuration
            # Otherwise: Use default configuration
            else:
                fast_apizr_configuration: FastApizrConfiguration = (
                    FastApizrConfiguration.model_validate(
                        {
                            "module_name": script_name.replace(".py", ""),
                            "api_filename": api_filename,
                        }
                    )
                )

            # Generate FastAPI app
            content = FastApiAnalyzr.model_validate_json(metadata)

            # Place the FastAPI app as result in the context
            context.result = ('FastApizr', FastApiAppGenerator(fast_apizr_configuration, content).gen_fastapi_app())
            context.status = 'success'

            # Save the FastAPI app
            context.write_output('FastApizr', api_filename)
            return context

        except FastApiAlreadyImplementedException:
            # Rename the script to `<basename>-api.py``
            api_filename = os.path.basename(script_name).replace(".py", "_api.py")
            output_api_filepath = output_dir / api_filename
            shutil.move(output_dir / script_name, output_api_filepath)
            return
        except Exception as e:
            context.add_log(message = "Error generating FastAPI app.", level="error")
            raise StepException(f"Failed to generate FastAPI application: {str(e)}") from e
        
    def validate(self, context):
        """
        Validate the step.
        
        :param context: A dictionary containing data shared across steps.
        """
        input_path: Path = context.input_path
        
        # Check if input_path is a valid path
        if not input_path.exists():
            raise StepException(f"'{input_path}' does not exist.")

    def prompt(self, context: Context):
        """
        Prompt the user for configuration.
        
        :param context: A dictionary containing data shared across steps.
        """
        _config: FastApizrConfiguration = context.config
        context.config: FastApizrConfiguration = ConfigPrompter(
            lang=context.lang).getConfiguration(
                version=_config.python_version,
                api_filename=_config.api_filename,
                module_name=_config.module_name,
                encoding=_config.encoding
            )
        return context
