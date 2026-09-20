import logging
from os import path

from jinja2 import Template

from apizr.modules.dockerizr.configuration import DockerizrConfiguration
from apizr.output import output_path, write_new_text

from .errorLogger import LogError


class GunicornGenerator:
    """
    Generates the necessary Gunicorn configuration files using provided settings.

    This class uses Jinja2 templates to generate the WSGI and Gunicorn configuration
    files required to run the FastAPI application with Gunicorn.

    Attributes:
        conf (Configuration): An instance of the Configuration class containing all necessary configuration data.
    """

    def __init__(self, conf: DockerizrConfiguration):
        """
        Initializes the GunicornGenerator with the provided configuration.

        Args:
            conf (Configuration): An instance of the Configuration class.
        """
        self.conf = conf

    @LogError(logging)
    def generate_gunicorn(self):
        """
        Generates the WSGI and Gunicorn configuration files.

        The generated files are saved in the project's main folder.
        """
        targets = [
            output_path(self.conf.project_path, self.conf.server.wsgi_file_name),
            output_path(self.conf.project_path, self.conf.server.wsgi_conf_file_name),
        ]
        if targets[0] == targets[1]:
            raise ValueError("Gunicorn output filenames must be distinct")
        for target in targets:
            if target.exists() or target.is_symlink():
                raise FileExistsError(f"Generated output already exists: {target}")
        write_new_text(targets[0], self.gunicorn_wsgi_generator())
        write_new_text(targets[1], self.gunicorn_conf_generator())

    @LogError(logging)
    def gunicorn_conf_generator(self) -> str:
        """
        Generates the Gunicorn configuration content using a Jinja2 template.

        Returns:
            str: The generated content for the Gunicorn configuration file.
        """
        with open(
            path.join(path.dirname(__file__), "templates/wsgi-conf.jinja"), "r"
        ) as f:
            template = Template(f.read())
            output = template.render(
                workers=self.conf.server.workers,
                host=self.conf.server.host,
                port=self.conf.server.port,
                timeout=self.conf.server.timeout,
            )
            return output

    @LogError(logging)
    def gunicorn_wsgi_generator(self) -> str:
        """
        Generates the WSGI configuration content using a Jinja2 template.

        Returns:
            str: The generated content for the WSGI configuration file.
        """
        with open(path.join(path.dirname(__file__), "templates/wsgi.jinja"), "r") as f:
            template = Template(f.read())
            output = template.render(main=self.conf.module_name)
            return output
