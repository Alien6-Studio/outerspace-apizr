from abc import ABC, abstractmethod


class StepException(RuntimeError):
    pass


class Step(ABC):
    @abstractmethod
    def execute(self, context):
        pass

    def validate(self, context):
        if context.input_path is None or not context.input_path.is_file():
            raise StepException(f"Input file does not exist: {context.input_path}")

    def prompt(self, context):
        return context
