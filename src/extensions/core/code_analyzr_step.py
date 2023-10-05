import importlib
import json
import os
import shutil

from pathlib import Path
from extensions.context import Context
from extensions.step import Step, StepException

from modules.code_analyzr.analyzr.astAnalyzr import AstAnalyzr
from modules.code_analyzr.configuration import CodeAnalyzrConfiguration
from modules.code_analyzr.prompt import ConfigPrompter

class CodeAnalyzrStep(Step):
    """
    A step that transforms a notebook using the notebook transformr module
    """

    def __init__(self) -> None:
        super().__init__()


    def __is_local_modules(self, module_name, input_path):
        """
        Check if a module is a local module or a standard/package module.
        """
        try:
            # Try to import the module (this check fails)
            result = importlib.import_module(module_name)
            return input_path in result.__file__
        except ImportError:
            return True

    def __copy_local_modules(self, metadata: str, input_path: Path, output_path: Path):
        """
        Check if the imports are local modules to copy them in the output directory.
        """
        json_metadata = json.loads(metadata)

        for import_data in json_metadata["imports_from"]:
            module_name = import_data["module"]
            if self.__is_local_modules(module_name, os.path.abspath(input_path.parent)):
                s = str(Path(input_path.parent, module_name)).split(".")[0]
                local_module_path = Path(s)
                dest_path = Path(output_path, s)
                local_file = Path(module_name + ".py")

                # Case where the module is a directory
                if local_module_path.exists() and not dest_path.exists():
                    dest_path = Path(output_path, local_module_path.name)
                    shutil.copytree(local_module_path, dest_path)

                # Case where the module is a file
                elif local_file.exists():
                    shutil.copy(local_file, output_path)

    def execute(self, context: Context) -> Context:
        """
        Execute the step.
        
        :param context: A dictionary containing data shared across steps.
        """

        # Get context
        self.validate(context)
        configuration: CodeAnalyzrConfiguration = context.config
        input_path: Path  = context.input_path # Path to the script
        output_dir: Path = context.output_dir

        # Read the code and place it in the context
        context.read_input()

        # Generate Metadata from code
        try:
            # Case 1 Prompt the user for configuration
            if context.prompt:
                code_analyzr_configuration = self.prompt(context).config
            # Case 2 : Use the configuration w/o prompting when requested
            elif context.config:
                code_analyzr_configuration = configuration
            # Otherwise: Use default configuration
            else:
                code_analyzr_configuration = CodeAnalyzrConfiguration()

            # Generate metadata
            metadata = AstAnalyzr(code_analyzr_configuration, context.data).get_analyse()

            # Place the metadata as result in the context
            context.result = ('CodeAnalyzr', metadata)
            context.status = 'success'

            # Save the metadata
            if output_dir is not None:
                metadata_name = input_path.stem + ".json"
                context.write_output('CodeAnalyzr', metadata_name)
                # Copy source code
                shutil.copy(input_path, output_dir)
                self.__copy_local_modules(metadata, input_path, output_dir)

            return context

        except Exception as e:
            raise StepException(f"Failed to generate metadata from code: {str(e)}") from e
        
    def validate(self, context: Context):
        """
        Validate the step.
        
        :param context: A dictionary containing data shared across steps.
        """
        input_path: Path = context.input_path

      # Check if input_path is a valid path
        if input_path and not input_path.exists():
            raise StepException(f"'{input_path}' does not exist.")
        
        if input_path and input_path.suffix == ".py":
        # For now, we just check the extension. In the future, you might want to add more checks
        # like checking for valid Python syntax.
            pass
    
    def prompt(self, context: Context):
        """
        Prompt the user when the configuration has not been provided.
        
        :param context: A dictionary containing data shared across steps.
        """
        _config: CodeAnalyzrConfiguration = context.config
        context.config: CodeAnalyzrConfiguration = ConfigPrompter(
            code_str=context.data, 
            lang=context.lang).getConfiguration(
                version=_config.python_version,
                encoding=_config.encoding)
        return context
