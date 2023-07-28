import logging
from os import path
from jinja2 import Template

from .configuration import Configuration
from .errorLogger import LogError


class GunicornGenerator:
    """
    Generates the necessary Gunicorn configuration files using provided settings.

    This class uses Jinja2 templates to generate the WSGI and Gunicorn configuration
    files required to run the FastAPI application with Gunicorn.

    Attributes:
        conf (Configuration): An instance of the Configuration class containing all necessary configuration data.
    """

    def __init__(self, conf: Configuration):
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

        The generated files are saved in the project's main folder, as specified in the configuration.
        """
        home_path = path.join(
            self.conf.project.project_path, self.conf.project.main_folder
        )
        with open(path.join(home_path, self.conf.server.wsgi_file_name), "w") as f:
            f.write(self.gunicorn_wsgi_generator())

        with open(path.join(home_path, self.conf.server.wsgi_conf_file_name), "w") as f:
            f.write(self.gunicorn_conf_generator())

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
                nb_workers=self.conf.server.nb_workers,
                host=self.conf.server.host,
                port=self.conf.server.port,
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
            output = template.render(main=self.conf.apizer.api_file_name[:-3])
            return output
