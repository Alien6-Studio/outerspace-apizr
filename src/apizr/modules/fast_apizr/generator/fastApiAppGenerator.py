import keyword
from pathlib import Path

from jinja2 import Environment, StrictUndefined


class FastApiAppGenerator:
    """Render routes from metadata; resolve runtime types in the original module."""

    def __init__(self, conf, analyse):
        self.conf = conf
        self.analyse = analyse

    def gen_fastapi_app(self):
        for name in self.conf.module_name.split("."):
            if not name.isidentifier() or keyword.iskeyword(name):
                raise ValueError("module_name must be a valid Python module path")
        functions = [f for f in self.analyse.functions if f.selected]
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
