"""Lexical class inventory; never instantiate classes or resolve decorators."""

import ast


def describe_class(node: ast.ClassDef, parent: str = "") -> dict:
    qualified_name = f"{parent}.{node.name}" if parent else node.name
    methods = []
    classes = []
    for member in node.body:
        if isinstance(member, ast.ClassDef):
            classes.append(describe_class(member, qualified_name))
        elif isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decorators = [ast.unparse(value) for value in member.decorator_list]
            # These describe syntax, not a claim that a builtin wasn't shadowed.
            kind = "instance"
            if decorators:
                kind = (
                    decorators[0]
                    if decorators in (["classmethod"], ["staticmethod"], ["property"])
                    else "decorated"
                )
            methods.append(
                {
                    "name": member.name,
                    "qualified_name": f"{qualified_name}.{member.name}",
                    "kind": kind,
                    "parameters": ast.unparse(member.args),
                    "returns": ast.unparse(member.returns) if member.returns else None,
                    "decorators": decorators,
                    "is_async": isinstance(member, ast.AsyncFunctionDef),
                    "line": member.lineno,
                }
            )
    return {
        "name": node.name,
        "qualified_name": qualified_name,
        "bases": [ast.unparse(base) for base in node.bases],
        "keywords": [ast.unparse(value) for value in node.keywords],
        "decorators": [ast.unparse(value) for value in node.decorator_list],
        "line": node.lineno,
        "methods": methods,
        "classes": classes,
    }
