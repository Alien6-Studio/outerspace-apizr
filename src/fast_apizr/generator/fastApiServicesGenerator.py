import logging
from os import path

from jinja2 import Template

from configuration import FastApizrConfiguration

from .analyzr.function import Function
from .errorLogger import LogError
from .modelGenerator import ModelGenerator


class FastApiServicesGenerator:
    """Responsible for generating the code for FastAPI services.

    This class uses the provided function information and configuration to generate
    the code for FastAPI services. It leverages Jinja2 templates to create the service code.
    """

    function: Function
    conf: FastApizrConfiguration

    def __init__(self, function: Function, conf: FastApizrConfiguration):
        """Initialize the FastApiServicesGenerator with the given function and configuration.

        Args:
            function (Function): The function details for which the service code needs to be generated.
            conf (Configuration): The configuration details for the service code generation.
        """
        self.function = function
        self.conf = conf

    @LogError(logging)
    def gen_service_code(self) -> str:
        """Generate the FastAPI service code based on the function and configuration.

        This method generates the service code using a Jinja2 template and the details
        from the provided function and configuration.

        Returns:
            str: The generated FastAPI service code.
        """
        schema = ModelGenerator(self.function.name, self.function.args)

        with open(path.join(path.dirname(__file__), "templates/service.j2"), "r") as f:
            template = Template(f.read())
            output = template.render(
                service_name=self.function.name + "_service",
                service_url="/" + self.function.name,
                schema_name=schema.name,
                schema=schema.gen_schema_code(),
                module_name=self.conf.module_name,
                function_name=self.function.name,
                args_list=self.get_arg_list(),
            )
            return output

    @LogError(logging)
    def get_arg_list(self):
        """Generate a list of arguments for the service based on the function's arguments.

        This method creates a list of arguments in a specific format to be used in the service code.

        Returns:
            str: A string representation of the list of arguments.
        """
        return ", ".join(
            [f"{arg.name} = arguments.{arg.name}" for arg in self.function.args]
        )


# @TODO: Consider adding error handling for potential issues during template rendering or code generation.
