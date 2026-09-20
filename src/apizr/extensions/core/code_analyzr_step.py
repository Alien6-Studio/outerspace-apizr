import ast
import keyword
import shutil

from ...modules.code_analyzr.analyzr.astAnalyzr import AstAnalyzr
from ..context import ContextStatus
from ..step import Step


def copy_local_modules(source, source_dir, output_dir, seen=None):
    """Copy local Python imports without importing them or executing user code."""
    seen = seen if seen is not None else set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module.split(".")[0]]
        else:
            continue
        for name in names:
            if name in seen:
                continue
            seen.add(name)
            local = source_dir / f"{name}.py"
            package = source_dir / name
            if local.is_file():
                if not local.resolve().is_relative_to(source_dir.resolve()):
                    raise ValueError(f"Local module escapes source directory: {local}")
                destination = output_dir / local.name
                if destination.exists() and destination.resolve() != local.resolve():
                    raise ValueError(
                        f"Local module collides with generated file: {destination.name}"
                    )
                if local.resolve() != destination.resolve():
                    shutil.copyfile(local, destination)
                copy_local_modules(
                    local.read_text(encoding="utf-8"), source_dir, output_dir, seen
                )
            elif package.is_dir() and (package / "__init__.py").is_file():
                if package.is_symlink():
                    raise ValueError(f"Symlink packages are not supported: {package}")
                for child in package.rglob("*"):
                    if child.is_symlink():
                        raise ValueError(
                            f"Symlinks in local packages are not supported: {child}"
                        )
                destination = output_dir / name
                shutil.copytree(
                    package,
                    destination,
                    ignore=shutil.ignore_patterns("__pycache__", ".*", "*.pyc"),
                )
                for child in package.rglob("*.py"):
                    copy_local_modules(
                        child.read_text(encoding="utf-8"), source_dir, output_dir, seen
                    )


class CodeAnalyzrStep(Step):
    def execute(self, context):
        self.validate(context)
        name = context.input_path.stem
        if not name.isidentifier() or keyword.iskeyword(name):
            raise ValueError(
                "The source filename must be a valid Python module name (letters, digits and underscores)"
            )
        source = context.input_path.read_text(encoding=context.config.encoding)
        metadata = AstAnalyzr(context.config, source).get_analyse()
        context.result = ("CodeAnalyzr", metadata)
        context.write_output("CodeAnalyzr", name + ".json")
        destination = context.output_dir / context.input_path.name
        if destination.resolve() != context.input_path.resolve():
            shutil.copyfile(context.input_path, destination)
        copy_local_modules(source, context.source_dir, context.output_dir, {name})
        context.status = ContextStatus.SUCCESS
        return context
