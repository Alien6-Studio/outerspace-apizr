"""Infer dependencies from imports without executing modules or contacting a registry."""

import ast
from pathlib import Path

from packaging.requirements import Requirement

from src.compat import DEFAULT_PYTHON, metadata, stdlib_module_names

ALIASES = {
    "sklearn": "scikit-learn",
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
}


class RequirementsAnalyzr:
    def __init__(self, config):
        self.config = config

    def generate_requirements(self, explicit=None):
        directory = Path(self.config.project_path)
        if not directory.is_dir():
            raise ValueError(f"Project directory does not exist: {directory}")
        requirements = set()
        if explicit:
            # Keep dependencies auditable and self-contained; reject includes and pip options.
            for line in Path(explicit).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                req = Requirement(line)
                requirements.add(str(req))
        else:
            distributions = metadata.packages_distributions()
            local = {p.stem for p in directory.glob("*.py")} | {
                p.name for p in directory.iterdir() if p.is_dir()
            }
            imports = set()
            for file in directory.rglob("*.py"):
                for node in ast.walk(
                    ast.parse(file.read_text(encoding=self.config.encoding))
                ):
                    if isinstance(node, ast.Import):
                        imports.update(alias.name.split(".")[0] for alias in node.names)
                    elif (
                        isinstance(node, ast.ImportFrom)
                        and node.module
                        and not node.level
                    ):
                        imports.add(node.module.split(".")[0])
            for name in sorted(imports - local - stdlib_module_names()):
                candidates = distributions.get(name, [])
                if len(candidates) > 1:
                    raise ValueError(
                        f"Ambiguous distribution for {name}; supply --requirements"
                    )
                distribution = ALIASES.get(name) or (
                    candidates[0] if candidates else name.replace("_", "-")
                )
                try:
                    requirement = (
                        f"{distribution}=={metadata.version(distribution)}"
                        if self.config.python_version == DEFAULT_PYTHON
                        else distribution
                    )
                except metadata.PackageNotFoundError:
                    requirement = distribution
                requirements.add(requirement)
        # Keep conditional requirements and constraints instead of overwriting by name.
        # pip intersects repeated package constraints and reports incompatible pins.
        for item in self.config.apizr_requirements:
            requirements.add(str(Requirement(item)))
        (directory / "requirements.txt").write_text(
            "\n".join(sorted(requirements)) + "\n", encoding="utf-8"
        )
