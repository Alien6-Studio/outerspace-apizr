import json
import sys
from pathlib import Path

import pytest

from apizr.modules.code_analyzr.analyzr.astAnalyzr import AstAnalyzr
from apizr.modules.code_analyzr.configuration import CodeAnalyzrConfiguration
from apizr.modules.dockerizr.configuration import DockerizrConfiguration
from apizr.modules.dockerizr.generator.dockerfileGenerator import DockerfileGenerator
from apizr.modules.fast_apizr.generator.analyzr.annotation import Annotation
from apizr.modules.fast_apizr.generator.modelGenerator import ModelGenerator

FIXTURE_VERSION = "{}.{}".format(*min(sys.version_info[:2], (3, 11)))
FIXTURES = (
    Path(__file__).resolve().parent
    / f"fixtures/legacy/code-analyzr-{FIXTURE_VERSION}/templateTest"
)


@pytest.mark.parametrize("fixture", sorted(FIXTURES.glob("*.py")), ids=lambda p: p.stem)
def test_historical_ast_fixtures(fixture):
    result = json.loads(
        AstAnalyzr(CodeAnalyzrConfiguration(), fixture.read_text()).get_analyse()
    )
    expected = json.loads(fixture.with_suffix(".json").read_text())
    for key in ["functions", "imports", "imports_from"]:
        assert result[key] == expected[key]


@pytest.mark.parametrize("container", ["List", "Tuple"])
def test_legacy_model_generator_preserves_container(container):
    assert (
        ModelGenerator("f", []).get_annotation_fields(
            Annotation(type=container, of=[Annotation(type="int")])
        )
        == f"{container}[int]"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "Callable"},
        {"type": "Callable", "of": []},
        {"type": "Callable", "of": None},
    ],
    ids=["missing-arguments", "empty-arguments", "null-arguments"],
)
def test_issue_7_callable_without_arguments(payload):
    """The original issue must not regress to an IndexError during schema generation."""
    from typing import Callable

    from pydantic import BaseModel

    from apizr.modules.fast_apizr.generator.analyzr.argument import Argument

    generator = ModelGenerator(
        "callback",
        [Argument(name="callback", annotation=Annotation.model_validate(payload))],
    )
    namespace = {"BaseModel": BaseModel, "Callable": Callable}
    exec(generator.gen_schema_code(), namespace)

    def callback():
        return 42

    model = namespace[generator.name](callback=callback)
    assert model.callback() == 42


@pytest.mark.parametrize(
    "base, tag, install", [("debian", "slim", "apt-get"), ("alpine", "alpine", "apk")]
)
def test_system_dependencies_rendered(tmp_path, base, tag, install):
    (tmp_path / "requirements.txt").write_text("numpy>=2\nscikit-learn==1.6.0\n")
    config = DockerizrConfiguration(
        project_path=str(tmp_path),
        docker_image=base,
        docker_image_tag=tag,
        dependencies=[
            {"name": "numpy", "packages": ["gcc"]},
            {"name": "scikit_learn", "packages": ["g++"]},
        ],
        custom_packages=["jq"],
    )
    generator = DockerfileGenerator(config)
    assert generator.get_packages() == ["g++", "gcc", "jq"]
    output = generator.dockerfile_generator()
    assert install in output
    assert "g++ gcc jq" in output


def test_analyzer_is_repeatable_and_does_not_match_keywords_in_strings():
    analyzer = AstAnalyzr(
        CodeAnalyzrConfiguration(), 'def f():\n    return "match case"\n'
    )
    assert analyzer.get_analyse() == analyzer.get_analyse()


def test_explicit_requirements_keep_environment_markers(tmp_path):
    from apizr.modules.dockerizr.generator.requirementsAnalyzr import (
        RequirementsAnalyzr,
    )

    explicit = tmp_path / "explicit.txt"
    explicit.write_text(
        'numpy==1.26.4; python_version < "3.12"\nnumpy>=2; python_version >= "3.12"\npydantic==1.10.0\n'
    )
    RequirementsAnalyzr(
        DockerizrConfiguration(project_path=str(tmp_path))
    ).generate_requirements(explicit)
    result = (tmp_path / "requirements.txt").read_text()
    assert "numpy==1.26.4" in result
    assert "numpy>=2" in result
    # Retain both constraints so pip can report the incompatible pin, instead of silently accepting v1.
    assert "pydantic==1.10.0" in result
    assert "pydantic<3,>=2.10" in result
