from typing import Dict
from extensions.context import Context
from extensions.step import Step
from extensions.core import NotebookTransformrStep, CodeAnalyzrStep, FastApizrStep, DockerizrStep, RequirementsAnalyzrStep

class AutomationEngine:
    
    def __init__(self):
        self.steps: [tuple(str, Context)] = []


    def add_step(self, step_name: str, context: Context):
        """
        Add a step by its class name.
        """
        step = (step_name, context)
        self.steps.append(step)


    def run(self):
        """
        Run the automation engine.
        This method is responsible for running the steps in the correct order.
        The automation engine must not know about the steps nor their order.
        Each step has been setup with the appropriate context.
        """
        result: Dict(str, str) = ("","")
        for step_name, step_context in self.steps:
            step_instance: Step = self._instantiate_step(step_name)

            # Execute the step
            if step_instance:
                # Previous step result is placed in the context
                step_context.data = result 
                result_context = step_instance.execute(step_context)
                result = result_context.result if result_context else None


    def _instantiate_step(self, step_name: str):
        """
        Instantiate a step class based on its name.
        This is a helper function for the run() method.
        """
        step_class = globals().get(step_name)
        if step_class:
            return step_class()
        else:
            print(f"Unknown step: {step_name}")
            return None
