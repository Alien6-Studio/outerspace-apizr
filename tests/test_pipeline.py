import importlib
import json
import subprocess
import sys
from pathlib import Path

import nbformat
import pytest
from fastapi.testclient import TestClient

from apizr.main import convert

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def generated(tmp_path, monkeypatch):
    names = set()

    def generate(source, *, notebook=False, configuration=None, **options):
        name = f"sample_{len(names)}"
        names.add(name)
        path = tmp_path / (name + (".ipynb" if notebook else ".py"))
        if notebook:
            nbformat.write(
                nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(source)]),
                path,
            )
        else:
            path.write_text(source, encoding="utf-8")
        output = tmp_path / (name + "_output")
        result = convert(path, output, configuration=configuration, **options)
        monkeypatch.syspath_prepend(str(output))
        importlib.invalidate_caches()
        app = importlib.import_module(result["api_module"]).app
        return TestClient(app), output, result

    yield generate
    for name in list(sys.modules):
        if any(name == prefix or name.startswith(prefix + "_") for prefix in names):
            sys.modules.pop(name, None)


def test_complete_notebook(generated):
    client, output, result = generated(
        "from typing import List\n\ndef total(prices: List[float], tax: float = 0.2) -> float:\n    return round(sum(prices) * (1 + tax), 2)\n",
        notebook=True,
    )
    assert client.post("/total", json={"prices": [10, 20]}).json() == 36
    assert client.post("/total", json={"prices": "invalid"}).status_code == 422
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/openapi.json").json()["paths"]["/total"]
    assert {"Dockerfile", "requirements.txt", "start.sh", ".dockerignore"} <= set(
        result["files"]
    )
    assert f"{result['api_module']}:app" in (output / "start.sh").read_text()
    assert "USER apizr" in (output / "Dockerfile").read_text()


def test_signatures_and_runtime_types(generated):
    client, _, _ = generated("""from __future__ import annotations
from typing import List, Literal, Optional, Tuple
from typing_extensions import Annotated
from pydantic import BaseModel, Field

class Item(BaseModel):
    value: int

def typed(items: List[Item], pair: Tuple[int, str], choice: Literal["a", "b"], limit: Annotated[int, Field(gt=0)], extra: Optional[int] = None):
    return {"total": sum(item.value for item in items), "pair": pair, "extra": extra}

def positional(a: int, /, b: int = 2, *, scale: int = 3):
    return (a + b) * scale

async def asynchronous(name: str = "world"):
    return {"name": name}

def ping():
    return "pong"
""")
    response = client.post(
        "/typed",
        json={"items": [{"value": 4}], "pair": [1, "x"], "choice": "a", "limit": 2},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"total": 4, "pair": [1, "x"], "extra": None}
    assert client.post("/positional", json={"a": 1}).json() == 9
    assert client.post("/positional", json={"a": 1, "scale": 4}).json() == 12
    assert client.post("/asynchronous").json() == {"name": "world"}
    assert client.post("/ping").json() == "pong"


def test_errors_have_http_status(generated):
    client, _, _ = generated(
        'from fastapi import HTTPException\n\ndef fail():\n    raise RuntimeError("sensitive detail")\n\ndef missing():\n    raise HTTPException(404, "missing")\n'
    )
    result = client.post("/fail")
    assert result.status_code == 500
    assert "sensitive" not in result.text
    assert client.post("/missing").status_code == 404


def test_custom_output_and_function_selection(tmp_path, generated):
    config = tmp_path / "configuration.yaml"
    config.write_text(
        "fast_apizr:\n  api_filename: custom_api.py\ncode_analyzr:\n  functions_to_analyze: chosen\n"
    )
    client, output, result = generated(
        "def chosen(x: int):\n    return x\n\ndef ignored():\n    return 1\n",
        configuration=config,
    )
    assert result["api_module"] == "custom_api"
    assert client.post("/chosen", json={"x": 2}).json() == 2
    assert client.post("/ignored").status_code == 404
    assert "custom_api:app" in (output / "start.sh").read_text()
    sys.modules.pop("custom_api", None)


def test_local_modules_are_copied_without_execution(tmp_path):
    marker = tmp_path / "executed"
    (tmp_path / "helper.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\nVALUE = 4\n"
    )
    source = tmp_path / "business.py"
    source.write_text("from helper import VALUE\n\ndef value():\n    return VALUE\n")
    output = tmp_path / "output"
    convert(source, output)
    assert (output / "helper.py").is_file()
    assert not marker.exists()
    assert "helper" not in (output / "requirements.txt").read_text()


def test_relative_imports_inside_local_package(tmp_path, monkeypatch):
    package = tmp_path / "local_package"
    package.mkdir()
    (package / "__init__.py").write_text("from .values import VALUE\n")
    (package / "values.py").write_text("VALUE = 7\n")
    source = tmp_path / "package_example.py"
    source.write_text(
        "from local_package import VALUE\n\ndef value():\n    return VALUE\n"
    )
    output = tmp_path / "output"
    result = convert(source, output)
    monkeypatch.syspath_prepend(str(output))
    try:
        client = TestClient(importlib.import_module(result["api_module"]).app)
        assert client.post("/value").json() == 7
    finally:
        for name in [
            "local_package",
            "local_package.values",
            "package_example",
            "package_example_api",
        ]:
            sys.modules.pop(name, None)


def test_cli_runs_outside_repository(tmp_path):
    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "apizr.main",
            "--notebook",
            str(ROOT / "examples/pricing.ipynb"),
            "--output-dir",
            str(output),
            "--force",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["api_module"] == "pricing_api"
    assert (output / "Dockerfile").exists()


@pytest.mark.parametrize(
    "source, message",
    [
        ("def flexible(*args):\n    return args\n", "args"),
        ("def flexible(**kwargs):\n    return kwargs\n", "kwargs"),
        ("x = 1\n", "No functions"),
    ],
)
def test_unsupported_input_is_actionable(tmp_path, source, message):
    path = tmp_path / "input.py"
    path.write_text(source)
    with pytest.raises(ValueError, match=message):
        convert(path, tmp_path / "output")


def test_notebook_magics_rejected(tmp_path):
    source = tmp_path / "magic.ipynb"
    nbformat.write(
        nbformat.v4.new_notebook(
            cells=[nbformat.v4.new_code_cell('get_ipython().system("echo unwanted")')]
        ),
        source,
    )
    with pytest.raises(ValueError, match="magics"):
        convert(source, tmp_path / "output")


def test_nonempty_output_is_preserved(tmp_path):
    source = tmp_path / "source.py"
    source.write_text("def hello():\n    return 1\n")
    output = tmp_path / "output"
    output.mkdir()
    marker = output / "important.txt"
    marker.write_text("keep me")
    with pytest.raises(ValueError, match="not empty"):
        convert(source, output)
    assert marker.read_text() == "keep me"


def test_skip_flags_and_explicit_requirements(tmp_path):
    source = tmp_path / "source.py"
    source.write_text("def hello():\n    return 1\n")
    req = tmp_path / "deps.txt"
    req.write_text("numpy==2.2.0\n")
    output = tmp_path / "output"
    convert(source, output, requirements=req, skip_pipreqs=True)
    requirements = (output / "requirements.txt").read_text()
    assert "numpy==2.2.0" in requirements
    assert "uvicorn[standard]" in requirements
    assert "fastapi" in requirements
    convert(
        source,
        tmp_path / "metadata",
        skip_fastapi=True,
        skip_docker=True,
        skip_pipreqs=True,
    )
    assert not (tmp_path / "metadata" / "Dockerfile").exists()
    with pytest.raises(ValueError, match="requires --skip-docker"):
        convert(source, tmp_path / "invalid", skip_fastapi=True)


def test_parameter_names_do_not_collide_with_pydantic(generated):
    client, _, _ = generated(
        "def names(_value: int, model_dump: int):\n    return _value + model_dump\n"
    )
    response = client.post("/names", json={"_value": 2, "model_dump": 3})
    assert response.status_code == 200, response.text
    assert response.json() == 5


def test_standalone_module_clis(tmp_path):
    source = tmp_path / "business.py"
    source.write_text("def add(a: int, b: int = 1):\n    return a + b\n")
    metadata = tmp_path / "metadata.json"
    output = tmp_path / "output"
    commands = [
        [
            "apizr.modules.code_analyzr.main",
            str(source),
            "--force",
            "--output",
            str(metadata),
        ],
        [
            "apizr.modules.fast_apizr.main",
            str(metadata),
            "--force",
            "--module_name",
            "business",
            "--api_filename",
            "business_api.py",
            "--output",
            str(output),
        ],
        [
            "apizr.modules.dockerizr.main",
            "--force",
            "--project_path",
            str(output),
            "--module_name",
            "business_api",
        ],
    ]
    for args in commands:
        result = subprocess.run(
            [sys.executable, "-m", *args], cwd=tmp_path, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
    assert "business_api:app" in (output / "start.sh").read_text()
