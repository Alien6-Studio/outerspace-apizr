import json
from importlib import metadata

import pytest

from apizr.main import convert
from apizr.modules.dockerizr.configuration import DockerizrConfiguration
from apizr.modules.dockerizr.generator.requirementsAnalyzr import RequirementsAnalyzr
from apizr.modules.notebook_transformr.transformr.nbTransformr import NotebookTransformr

from .support import analyze, contents, generate, runtime


def requirements(root, source, monkeypatch, distributions=None):
    root.mkdir(exist_ok=True)
    (root / "main.py").write_text(source)
    monkeypatch.setattr(metadata, "packages_distributions", lambda: distributions or {})

    def version(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "version", version)
    RequirementsAnalyzr(
        DockerizrConfiguration(project_path=str(root), apizr_requirements=[])
    ).generate_requirements()
    return (root / "requirements.txt").read_text().splitlines()


@pytest.mark.parametrize(
    "statement",
    [
        "import foreign",
        "import foreign.submodule",
        "import foreign as alias",
        "from foreign import value",
        "from foreign.submodule import value",
    ],
)
def test_static_import_forms_map_to_distribution(tmp_path, monkeypatch, statement):
    assert requirements(
        tmp_path, statement, monkeypatch, {"foreign": ["distribution-name"]}
    ) == ["distribution-name"]


def test_dependency_walk_is_broader_than_callable_metadata(tmp_path, monkeypatch):
    source = """import importlib
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import type_only
if False:
    import dead_code
def call():
    import inside_function
    return importlib.import_module("dynamic_package")
class C:
    import inside_class
from . import sibling
__import__("also_dynamic")
"""
    static = json.loads(analyze(source))
    assert [item["name"] for item in static["imports"]] == [
        "importlib",
        "type_only",
        "dead_code",
    ]
    assert requirements(tmp_path, source, monkeypatch) == [
        "dead-code",
        "inside-class",
        "inside-function",
        "type-only",
    ]


def test_aliases_unknown_names_and_ambiguous_distributions(tmp_path, monkeypatch):
    assert requirements(
        tmp_path, "import yaml\nimport PIL\nimport unknown_name\n", monkeypatch
    ) == ["Pillow", "PyYAML", "unknown-name"]
    (tmp_path / "requirements.txt").unlink()
    with pytest.raises(ValueError, match="Ambiguous distribution.*--requirements"):
        requirements(
            tmp_path, "import ambiguous", monkeypatch, {"ambiguous": ["one", "two"]}
        )


def test_circular_local_imports_are_copied_once_without_execution(tmp_path):
    (tmp_path / "a.py").write_text('import b\nraise RuntimeError("must not execute")\n')
    (tmp_path / "b.py").write_text("import a\n")
    output = generate(tmp_path, "import a\ndef value(): return 1\n")
    assert {"a.py", "b.py"} <= set(contents(output))
    inferred = (output / "requirements.txt").read_text().splitlines()
    assert not any(
        line.startswith(("a==", "b==")) or line in {"a", "b"} for line in inferred
    )


def test_namespace_and_root_relative_imports_are_not_bundled(tmp_path):
    namespace = tmp_path / "namespace_pkg"
    namespace.mkdir()
    (namespace / "value.py").write_text("VALUE = 1\n")
    (tmp_path / "sibling.py").write_text("VALUE = 2\n")
    output = generate(
        tmp_path,
        "import namespace_pkg.value\nfrom .sibling import VALUE\ndef value(): return VALUE\n",
    )
    assert not (output / "namespace_pkg").exists()
    assert not (output / "sibling.py").exists()
    assert "namespace-pkg" in (output / "requirements.txt").read_text().splitlines()


def test_file_package_collision_prefers_file_during_copy(tmp_path):
    (tmp_path / "shared.py").write_text("VALUE = 'file'\n")
    package = tmp_path / "shared"
    package.mkdir()
    (package / "__init__.py").write_text("VALUE = 'package'\n")
    output = generate(tmp_path, "import shared\ndef value(): return shared.VALUE\n")
    assert (output / "shared.py").exists()
    assert not (output / "shared").exists()
    with runtime(output) as client:
        assert client.post("/value").json() == "file"


def test_stdlib_shadowing_is_copied_but_not_declared_external(tmp_path):
    (tmp_path / "json.py").write_text("VALUE = 1\n")
    output = generate(tmp_path, "import json\ndef value(): return 1\n")
    assert (output / "json.py").exists()
    assert "json" not in (output / "requirements.txt").read_text().splitlines()
    # Do not import: stdlib shadowing depends on process import-cache state.


@pytest.mark.parametrize("kind", ["module", "package", "nested-package-link"])
def test_import_symlink_escapes_are_rejected(tmp_path, kind):
    source_root = tmp_path / "source"
    source_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "__init__.py").write_text("VALUE = 1\n")
    (outside / "module.py").write_text("VALUE = 2\n")
    if kind == "module":
        (source_root / "linked.py").symlink_to(outside / "module.py")
    elif kind == "package":
        (source_root / "linked").symlink_to(outside, target_is_directory=True)
    else:
        (source_root / "linked").mkdir()
        (source_root / "linked/__init__.py").write_text("")
        (source_root / "linked/nested").symlink_to(outside, target_is_directory=True)
    before = contents(outside)
    with pytest.raises(ValueError, match="[Ss]ymlink|escapes source"):
        generate(source_root, "import linked\ndef value(): return 1\n")
    assert contents(outside) == before
    assert not (source_root / "output/linked").exists()
    assert not (source_root / "output/linked.py").exists()


@pytest.mark.parametrize(
    "filename",
    [
        "../escape.py",
        "/tmp/escape.py",
        "..\\escape.py",
        "C:\\escape.py",
        "contract_source.py",
        "helper.py",
    ],
)
def test_api_filename_cannot_escape_or_replace_user_modules(tmp_path, filename):
    helper = tmp_path / "helper.py"
    helper.write_text("VALUE = 'keep'\n")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"fast_apizr": {"api_filename": filename}}))
    with pytest.raises(ValueError, match="filename|overwrite"):
        generate(
            tmp_path,
            "import helper\ndef value(): return helper.VALUE\n",
            configuration=config,
        )
    assert helper.read_text() == "VALUE = 'keep'\n"
    if (tmp_path / "output/helper.py").exists():
        assert (tmp_path / "output/helper.py").read_bytes() == helper.read_bytes()


def test_local_module_colliding_with_default_api_is_preserved(tmp_path):
    helper = tmp_path / "contract_source_api.py"
    helper.write_text("VALUE = 7\n")
    with pytest.raises(ValueError, match="overwrite"):
        generate(tmp_path, "import contract_source_api\ndef value(): return 1\n")
    assert (
        tmp_path / "output/contract_source_api.py"
    ).read_bytes() == helper.read_bytes()


def test_source_output_overlap_is_rejected_before_writes(tmp_path):
    source = tmp_path / "input.py"
    source.write_text("def value(): return 1\n")
    before = contents(tmp_path)
    with pytest.raises(ValueError, match="separate directory"):
        convert(source, tmp_path)
    assert contents(tmp_path) == before


def test_package_copy_must_not_recurse_into_its_own_output(tmp_path, monkeypatch):
    package = tmp_path / "local_pkg"
    package.mkdir()
    (package / "__init__.py").write_text("VALUE = 1\n")
    source = tmp_path / "source.py"
    source.write_text("import local_pkg\ndef value(): return 1\n")

    # Prove rejection before copytree starts; never build a recursion bomb in CI.
    def should_not_copy(*args, **kwargs):
        pytest.fail("copytree would recursively copy its own destination")

    monkeypatch.setattr(
        "apizr.extensions.core.code_analyzr_step.shutil.copytree", should_not_copy
    )
    with pytest.raises(ValueError, match="[Oo]utput.*package"):
        convert(source, package / "generated")


def test_notebook_script_writer_preserves_existing_file_and_symlink(tmp_path):
    target = tmp_path / "notebook.py"
    target.write_text("USER DATA\n")
    with pytest.raises(FileExistsError):
        NotebookTransformr().save_script(
            "def value(): return 1\n", tmp_path, "notebook.ipynb"
        )
    assert target.read_text() == "USER DATA\n"
    target.unlink()
    outside = tmp_path / "outside.txt"
    outside.write_text("OUTSIDE\n")
    target.symlink_to(outside)
    with pytest.raises(FileExistsError):
        NotebookTransformr().save_script(
            "def value(): return 1\n", tmp_path, "notebook.ipynb"
        )
    assert outside.read_text() == "OUTSIDE\n"


def test_local_module_symlink_within_source_tree_is_copied(tmp_path):
    (tmp_path / "actual.py").write_text("VALUE = 1\n")
    (tmp_path / "alias.py").symlink_to(tmp_path / "actual.py")
    output = generate(tmp_path, "import alias\ndef value(): return alias.VALUE\n")
    assert (output / "alias.py").read_bytes() == (tmp_path / "actual.py").read_bytes()
    assert not (output / "alias.py").is_symlink()


def test_context_writer_never_overwrites_an_existing_output(tmp_path):
    from apizr.configuration import MainConfiguration
    from apizr.extensions.context import Context

    target = tmp_path / "existing.json"
    target.write_text("USER DATA\n")
    context = Context()
    context.config = MainConfiguration()
    context.output_dir = tmp_path
    context.result = ("metadata", "replacement")
    with pytest.raises(FileExistsError):
        context.write_output("metadata", "existing.json")
    assert target.read_text() == "USER DATA\n"


@pytest.mark.parametrize(
    "name", ["Dockerfile", "start.sh", ".dockerignore", "entrypoint.sh"]
)
def test_standalone_docker_generation_preserves_existing_files(tmp_path, name):
    from apizr.modules.dockerizr.generator.dockerfileGenerator import (
        DockerfileGenerator,
    )

    (tmp_path / "requirements.txt").write_text("fastapi\n")
    (tmp_path / name).write_text("USER DATA\n")
    before = contents(tmp_path)
    config = DockerizrConfiguration(
        project_path=str(tmp_path), entrypoint="echo startup"
    )
    with pytest.raises(FileExistsError):
        DockerfileGenerator(config).generate_dockerfile()
    assert contents(tmp_path) == before


def test_requirements_writer_preserves_explicit_user_file(tmp_path):
    (tmp_path / "main.py").write_text("import json\n")
    path = tmp_path / "requirements.txt"
    path.write_text("USER DATA\n")
    with pytest.raises(FileExistsError):
        RequirementsAnalyzr(
            DockerizrConfiguration(project_path=str(tmp_path))
        ).generate_requirements()
    assert path.read_text() == "USER DATA\n"


@pytest.mark.parametrize(
    "filename",
    [
        "../escape.py",
        "/tmp/apizr-characterization-escape.py",
        "..\\escape.py",
        "C:\\escape.py",
    ],
)
def test_standalone_fastapi_output_filename_is_contained(tmp_path, filename):

    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(analyze("def value(): return 1\n"))
    output = tmp_path / "output"
    # Stub the writer in-process: a failing pre-fix test must not write outside tmp_path.
    from types import SimpleNamespace

    from apizr.modules.fast_apizr import main

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            main,
            "handle_args",
            lambda: SimpleNamespace(
                file=str(metadata_path),
                force=True,
                configuration=None,
                module_name="source",
                api_filename=filename,
                output=str(output),
                version=None,
                encoding=None,
            ),
        )

        def no_write(*args, **kwargs):
            pytest.fail("unsafe filename reached standalone writer")

        patch.setattr(main, "save_result", no_write)
        with pytest.raises(SystemExit) as error:
            main.main()
        assert error.value.code == 1


@pytest.mark.parametrize("field", ["wsgi_file_name", "wsgi_conf_file_name"])
def test_legacy_gunicorn_output_is_contained(tmp_path, field):
    from apizr.modules.dockerizr.generator.gunicornGenerator import GunicornGenerator

    directory = tmp_path / "output"
    directory.mkdir()
    config = DockerizrConfiguration(
        project_path=str(directory), server={field: "../escape.py"}
    )
    with pytest.raises(ValueError, match="filename"):
        GunicornGenerator(config).generate_gunicorn()
    assert not (tmp_path / "escape.py").exists()


@pytest.mark.parametrize("module", ["code_analyzr", "fast_apizr"])
def test_standalone_result_writer_never_overwrites(tmp_path, module):
    import importlib

    cli = importlib.import_module(f"apizr.modules.{module}.main")
    target = tmp_path / "existing.txt"
    target.write_text("USER DATA\n")
    with pytest.raises(cli.ConfigurationError):
        cli.save_result(target, "replacement")
    assert target.read_text() == "USER DATA\n"


def test_gunicorn_outputs_are_distinct_and_existing_files_preserved(tmp_path):
    from apizr.modules.dockerizr.generator.gunicornGenerator import GunicornGenerator

    config = DockerizrConfiguration(
        project_path=str(tmp_path),
        server={"wsgi_file_name": "same.py", "wsgi_conf_file_name": "same.py"},
    )
    with pytest.raises(ValueError, match="distinct"):
        GunicornGenerator(config).generate_gunicorn()
    config = DockerizrConfiguration(project_path=str(tmp_path))
    (tmp_path / "gunicorn.conf.py").write_text("USER DATA\n")
    before = contents(tmp_path)
    with pytest.raises(FileExistsError):
        GunicornGenerator(config).generate_gunicorn()
    assert contents(tmp_path) == before
