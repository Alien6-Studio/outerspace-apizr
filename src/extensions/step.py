import logging

from abc import ABC, abstractmethod
from extensions.context import Context

# Configure logging settings
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename="app_errors.log",
)
logger = logging.getLogger(__name__)

class StepException(Exception):
    """Base class for exceptions raised by steps."""
    
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class Step(ABC):

    @abstractmethod
    def execute(self, context: Context) -> Context:
        """
        Execute the step.
        
        :param context: A dictionary containing data shared across steps.
        """
        pass


    @abstractmethod
    def validate(self, context: Context):
        """
        Validate the step.
        
        :param context: A dictionary containing data shared across steps.
        """
        pass

    @abstractmethod
    def prompt(self, context: Context):
        """
        Prompt the user when the configuration has not been provided.
        
        :param context: A dictionary containing data shared across steps.
        """
        pass