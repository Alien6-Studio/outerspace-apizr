import logging
from os import path
from typing import List, Optional, Union

from jinja2 import Template

from .analyzr.annotation import Annotation
from .analyzr.argument import Argument
from .errorLogger import LogError


class ModelGenerator:
    """Responsible for generating the model code for FastAPI based on function arguments.

    This class uses the provided function arguments to generate the necessary model
    code for FastAPI. It takes into account various factors such as argument annotations
    and derived types to create the model representation.
    """

    name: str
    args: List[Argument]

    def __init__(self, name: str, args: List[Argument]):
        """Initialize the ModelGenerator with a given name and arguments.

        Args:
            name (str): The name for the model.
            args (List[Argument]): The arguments that will be represented in the model.
        """
        self.name = name.capitalize() + "_model"
        self.args = args

    @LogError(logging)
    def get_fields(self) -> dict:
        """Retrieve the fields for the model based on the arguments.

        Returns:
            dict: A dictionary containing fields mapped to their types.
        """
        fields = {}
        for arg in self.args:
            fields[arg.name] = self.get_annotation_fields(arg.annotation)
        return fields

    @LogError(logging)
    def get_annotation_fields(self, annotation: Annotation) -> str:
        """Retrieve the field type based on its annotation.

        Args:
            annotation (Annotation): The annotation for the field.

        Returns:
            str: The type representation for the field.
        """
        if annotation is None or annotation.type == "any":
            return "Any"
        if annotation.type == "Callable":
            if annotation.of and isinstance(annotation.of[0], Annotation):
                return "Callable" + self.get_annotation_fields(annotation.of[0])
            elif annotation.of:
                return f"Callable[{annotation.of[0]}]"
            else:
                return "Callable"
        if annotation.type == "List" or annotation.type == "Tuple":
            return self.get_sub_type(annotation.of if annotation.of is not None else [])
        return annotation.type + (
            self.get_sub_type(annotation.of) if annotation.of else ""
        )

    def get_sub_type(self, annotations: List[Union[str, Annotation]]) -> str:
        """Retrieve the sub-type for composite types like List or Tuple.

        Args:
            annotations (List[Union[str, Annotation]]): The annotations for the composite type.

        Returns:
            str: The sub-type representation.
        """
        if not annotations:
            return ""
        elif len(annotations) > 1:
            return (
                "["
                + ", ".join(
                    [
                        self.get_annotation_fields(annot)
                        if isinstance(annot, Annotation)
                        else annot
                        for annot in annotations
                    ]
                )
                + "]"
            )
        else:
            if isinstance(annotations[0], Annotation):
                return "[" + self.get_annotation_fields(annotations[0]) + "]"
            else:
                return f"[{annotations[0]}]"

    @LogError(logging)
    def gen_schema_code(self) -> str:
        """Generate the FastAPI model code.

        Uses a Jinja2 template to render the model code based on the fields.

        Returns:
            str: The generated model code.
        """
        output = ""
        with open(path.join(path.dirname(__file__), "templates/schema.j2"), "r") as f:
            template = Template(f.read())
            if self.get_fields() not in [None, {}]:
                output = template.render(
                    schema_name=self.name, fields=self.get_fields().items()
                )
        return output
