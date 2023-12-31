import logging
from os import path

from jinja2 import Template

from configuration import FastApizrConfiguration

from .analyzr.analyzr import Analyzr
from .errorLogger import LogError
from .exceptions import FastApiAlreadyImplementedException
from .fastApiImportGenerator import FastApiImportGenerator
from .fastApiServicesGenerator import FastApiServicesGenerator


class FastApiAppGenerator:
    """Responsible for generating the code for a FastAPI application.

    This class uses the provided analysis and configuration to generate the code for a FastAPI application.
    It leverages Jinja2 templates and other generator classes for creating the complete application code.
    """

    analyse: Analyzr
    conf: FastApizrConfiguration

    def __init__(self, conf: FastApizrConfiguration, analyse: Analyzr):
        """Initialize the FastApiAppGenerator with the given configuration and analysis.

        Args:
            conf (Configuration): The configuration details for the FastAPI code generation.
            analyse (Analyzr): The analysis details to guide the code generation.
        """
        self.conf = conf
        self.analyse = analyse

    @LogError(logging)
    def gen_fastapi_app(self):
        """Generate the FastAPI application code based on the analysis and configuration.

        This method generates the imports, services, and other necessary code elements for the FastAPI application.
        It then fills a Jinja2 template with these details to produce the final application code.

        Returns:
            str: The generated FastAPI application code.
        """
        services = []
        for imp in self.analyse.imports_from:
            if imp.module == "fastapi":
                raise FastApiAlreadyImplementedException(
                    "FastAPI is already imported in the provided code. Please remove it and try again."
                )

        imports = FastApiImportGenerator(self.analyse).generate_import_code()

        for function in [f for f in self.analyse.functions if f.selected]:
            cl = FastApiServicesGenerator(function, self.conf)
            services.append(cl.gen_service_code())

        with open(
            path.join(path.dirname(__file__), "templates/fastApiApp.j2"), "r"
        ) as f:
            template = Template(f.read())

        return template.render(
            imports=imports, main_module=self.conf.module_name, services=services
        )
