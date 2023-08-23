import itertools
import logging

from os import path
from pprint import pprint
from typing import List

from .analyzr.analyzr import Analyzr
from .analyzr.imports import Import
from .analyzr.importFrom import ImportFrom
from .analyzr.annotation import Annotation
from .errorLogger import LogError


class FastApiImportGenerator:
    """Responsible for generating the code for FastAPI imports.

    This class uses the provided analysis to generate the necessary import
    statements for the FastAPI code. It takes into account various factors
    such as function annotations, direct imports, and import-from statements.
    """

    primitive_type = [
        "str",
        "int",
        "float",
        "complex",
        "list",
        "tuple",
        "range",
        "dict",
        "set",
        "frozenset",
        "bool",
        "bytes",
        "bytearray",
        "memoryview",
    ]

    def __init__(self, analyse: Analyzr):
        """Initialize the FastApiImportGenerator with the given analysis.

        Args:
            analyse (Analyzr): The analysis details to guide the import code generation.
        """
        self.analyse = analyse
        self.imports = list()
        self.get_imports()

    @LogError(logging)
    def get_imports(self):
        """Retrieve the list of necessary imports based on the analysis."""
        types = set()

        # Add imports from functions
        for function in self.analyse.functions:
            for arg in function.args:
                if arg.annotation:
                    for t in self.get_annotation_types(arg.annotation):
                        types.add(t)

        for t in types:
            if t in self.primitive_type:
                continue
            if t == "any":
                self.imports.append(
                    {
                        "imports": [{"asname": None, "name": "Any"}],
                        "level": 0,
                        "module": "typing",
                    }
                )
            else:
                a = self.lookup(t)
                if a:
                    self.imports.append(a[0])

    @LogError(logging)
    def lookup(self, type):
        """Search for a specific type among the imports.

        Args:
            type (str): The type name to search for.

        Returns:
            List[Import]: A list of matching import statements.
        """

        def search_in_import(imp: List[Import], type: str):
            # Test initial plus général
            matches = [im for im in imp if im.asname == type or im.name == type]

            # Si aucun match n'est trouvé avec le test général, utilisez le préfixe
            if not matches:
                # Split the type string to get the prefix
                prefix = type.split(".")[0] if "." in type else type
                matches = [im for im in imp if im.asname == prefix or im.name == prefix]
            return matches

        results = [
            import_from
            for import_from in self.analyse.imports_from
            if search_in_import(import_from.imports, type)
        ] + search_in_import(self.analyse.imports, type)
        if not results:
            return None
        return results

    @LogError(logging)
    def get_annotation_types(self, annotation: Annotation):
        """Extract types from a given annotation.

        Args:
            annotation (Annotation): The annotation from which types need to be extracted.

        Returns:
            List[str]: A list of type names extracted from the annotation.
        """
        if annotation is None:
            return []
        if isinstance(annotation.of, list):
            return list(
                itertools.chain(
                    *[self.get_annotation_types(of) for of in annotation.of]
                )
            ) + [annotation.type]
        return self.get_annotation_types(annotation.of) + [annotation.type]

    @LogError(logging)
    def generate_import_code(self):
        """Generate the import statements code based on the gathered imports.

        Returns:
            set: A set containing unique import statements.
        """
        result = set()
        for imp in self.imports:
            if isinstance(imp, ImportFrom):
                result.add(
                    "from "
                    + ("." * imp.level)
                    + imp.module
                    + " import "
                    + (
                        ", ".join(
                            [
                                im.name
                                + (
                                    (" as " + im.asname)
                                    if im.asname is not None
                                    else ""
                                )
                                for im in imp.imports
                            ]
                        )
                    )
                )
            elif isinstance(imp, Import):
                result.add(
                    "import "
                    + imp.name
                    + ((" as " + imp.asname) if imp.asname is not None else "")
                )

        return result
