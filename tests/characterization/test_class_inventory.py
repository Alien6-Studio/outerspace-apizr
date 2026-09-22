import json

import pytest

from apizr.modules.code_analyzr.analyzr.astAnalyzr import AstAnalyzr
from apizr.modules.code_analyzr.configuration import CodeAnalyzrConfiguration
from apizr.modules.fast_apizr.configuration import FastApizrConfiguration
from apizr.modules.fast_apizr.generator.analyzr.analyzr import Analyzr
from apizr.modules.fast_apizr.generator.fastApiAppGenerator import FastApiAppGenerator

from .support import analyze, generate, runtime


def test_class_inventory_preserves_declared_structure_without_execution(tmp_path):
    marker = tmp_path / "executed"
    source = f"""from pathlib import Path
@factory(Path({str(marker)!r}).touch())
class Service(Base, metaclass=Meta):
    @classmethod
    def create(cls, value: int = 3, /, *, name: str = "x") -> "Service": pass
    @staticmethod
    async def fetch(*args: int, **kwargs: str): pass
    @property
    def name(self): pass
    @custom
    @classmethod
    def decorated(cls): pass
    def run(self, value):
        def hidden(): pass
        class Hidden: pass
    class Nested:
        def run(self): pass
def entry(): return 1
"""
    analyzer = AstAnalyzr(CodeAnalyzrConfiguration(), source)
    result = json.loads(analyzer.get_analyse())
    assert result == json.loads(analyzer.get_analyse())
    assert not marker.exists()
    assert [f["name"] for f in result["functions"]] == ["entry"]
    cls = result["classes"][0]
    assert cls["qualified_name"] == "Service"
    assert cls["bases"] == ["Base"] and cls["keywords"] == ["metaclass=Meta"]
    assert cls["decorators"][0].startswith("factory(")
    assert [m["kind"] for m in cls["methods"]] == [
        "classmethod",
        "staticmethod",
        "property",
        "decorated",
        "instance",
    ]
    assert cls["methods"][0]["parameters"] == "cls, value: int=3, /, *, name: str='x'"
    assert cls["methods"][0]["returns"] == "'Service'"
    assert cls["methods"][1]["is_async"]
    assert cls["methods"][1]["parameters"] == "*args: int, **kwargs: str"
    assert cls["classes"][0]["methods"][0]["qualified_name"] == "Service.Nested.run"
    analyzer.code_str = "def only(): pass"
    assert "classes" not in json.loads(analyzer.get_analyse())


def test_class_metadata_does_not_create_routes_or_instantiate_classes(tmp_path):
    source = """class Service:
    def __init__(self): raise RuntimeError("must not instantiate")
    @classmethod
    def calculate(cls, value: int): return value + 1
def wrapper(value: int): return Service.calculate(value)
"""
    output = generate(tmp_path, source, skip_docker=True, skip_pipreqs=True)
    with runtime(output) as client:
        assert client.post("/wrapper", json={"value": 3}).json() == 4
        assert client.post("/calculate", json={"value": 3}).status_code == 404
        assert set(client.get("/openapi.json").json()["paths"]) == {"/wrapper"}


def test_selection_excludes_ambiguous_name_but_does_not_choose_one_definition():
    source = "def f(x): pass\ndef f(y): pass\ndef ok(): pass"
    for options in ({"ignore": "f"}, {"functions_to_analyze": "ok"}):
        assert [
            f["name"] for f in json.loads(analyze(source, **options))["functions"]
        ] == ["ok"]
    with pytest.raises(ValueError, match="Ambiguous function definitions"):
        analyze(source, functions_to_analyze="f")


def test_fastapi_rejects_duplicate_routes_from_external_metadata():
    data = json.loads(analyze("def f(): pass"))
    data["functions"] *= 2
    generator = FastApiAppGenerator(
        FastApizrConfiguration(), Analyzr.model_validate(data)
    )
    with pytest.raises(ValueError, match="duplicate route names"):
        generator.gen_fastapi_app()
