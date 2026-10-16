import keyword
import sys
import warnings
from pathlib import Path

from jinja2 import Environment, StrictUndefined


class FastApiAppGenerator:
    """Render routes from metadata; resolve runtime types in the original module."""

    def __init__(self, conf, analyse):
        self.conf = conf
        self.analyse = analyse

    def gen_fastapi_app(self):
        notice = (
            "The legacy FastAPI pipeline is deprecated and removed in 0.4.6. "
            "Migrate to apizr inspect, explicit exposure, and apizr generate rest/mcp."
        )
        warnings.warn(notice, DeprecationWarning, stacklevel=2)
        print("apizr: " + notice, file=sys.stderr)
        for name in self.conf.module_name.split("."):
            if not name.isidentifier() or keyword.iskeyword(name):
                raise ValueError("module_name must be a valid Python module path")
        functions = [f for f in self.analyse.functions if f.selected]
        names = [function.name for function in functions]
        if len(set(names)) != len(names):
            raise ValueError("Ambiguous function definitions: duplicate route names")
        for function in functions:
            for name in [function.name, *(arg.name for arg in function.args)]:
                if not name.isidentifier() or keyword.iskeyword(name):
                    raise ValueError(f"Invalid Python identifier: {name}")
        template = Environment(
            undefined=StrictUndefined, keep_trailing_newline=True
        ).from_string(
            Path(__file__)
            .with_name("templates")
            .joinpath("fastApiApp.j2")
            .read_text(encoding="utf-8")
        )
        return template.render(main_module=self.conf.module_name, functions=functions)
