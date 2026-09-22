import json
import subprocess
import sys
from pathlib import Path

import nbformat
import pytest

from apizr.legacy_delivery import build_image, copy_resources, resource_files
from apizr.main import convert, main


def notebook(tmp_path):
    path = tmp_path / "sample.ipynb"
    nbformat.write(
        nbformat.v4.new_notebook(
            cells=[nbformat.v4.new_code_cell("def f(x: int): return x + 1\n")]
        ),
        path,
    )
    return path


def test_one_command_notebook_configuration_dependencies_resources_and_image(
    tmp_path, monkeypatch, capsys
):
    source = notebook(tmp_path)
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/prices.json").write_text('{"rate": 2}')
    (tmp_path / "settings.json").write_text('{"name": "example"}')
    (tmp_path / "secret.txt").write_text("not selected")
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("packaging==26.0\n")
    config = tmp_path / "config.yaml"
    config.write_text("dockerizr:\n  server:\n    port: 5017\n    workers: 2\n")
    output = tmp_path / "out"
    calls = []

    def docker(command, **kw):
        calls.append(command)
        assert command[:4] == ["docker", "build", "--tag", "example:local"]
        assert command[-1] == str(output)
        assert "packaging==26.0" in (output / "requirements.txt").read_text()
        assert "--port 5017 --workers 2" in (output / "start.sh").read_text()
        assert (output / "assets/prices.json").read_text() == '{"rate": 2}'
        assert not (output / "secret.txt").exists()
        assert kw["check"] is True and kw["stdout"] is sys.stderr
        Path(command[5]).write_text("sha256:" + "a" * 64)

    monkeypatch.setattr("apizr.legacy_delivery.subprocess.run", docker)
    main(
        [
            "--notebook",
            str(source),
            "--output-dir",
            str(output),
            "--requirements",
            str(requirements),
            "--configuration",
            str(config),
            "--include",
            "assets",
            "--include",
            "settings.json",
            "--build-image",
            "example:local",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert len(calls) == 1
    assert result["image"] == {"tag": "example:local", "id": "sha256:" + "a" * 64}
    assert {"assets/prices.json", "settings.json"} <= set(result["files"])


def test_generation_never_builds_implicitly(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "apizr.legacy_delivery.subprocess.run",
        lambda *a, **kw: pytest.fail("implicit Docker build"),
    )
    result = convert(notebook(tmp_path), tmp_path / "out")
    assert "image" not in result
    assert "Dockerfile" in result["files"]


@pytest.mark.parametrize(
    "name",
    [
        "../outside",
        "/tmp/file",
        "C:\\file",
        "a/../file",
        ".",
        "",
        ".env",
        "data/.git/config",
    ],
)
def test_resource_paths_refused(tmp_path, name):
    (tmp_path / ".env").write_text("secret")
    (tmp_path / "data/.git").mkdir(parents=True)
    (tmp_path / "data/.git/config").write_text("secret")
    with pytest.raises(ValueError):
        resource_files(tmp_path, [name])


def test_symlinks_nonregular_missing_duplicates_and_collisions(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/item").write_text("content")
    (tmp_path / "link").symlink_to(tmp_path / "data", target_is_directory=True)
    for name in ("link", "link/item", "missing"):
        with pytest.raises(ValueError):
            resource_files(tmp_path, [name])
    with pytest.raises(ValueError, match="Repeated"):
        resource_files(tmp_path, ["data", "data/item"])
    if hasattr(__import__("os"), "mkfifo"):
        __import__("os").mkfifo(tmp_path / "pipe")
        with pytest.raises(ValueError, match="regular file"):
            resource_files(tmp_path, ["pipe"])
    files = resource_files(tmp_path, ["data"])
    output = tmp_path / "out"
    output.mkdir()
    (output / "data").symlink_to(tmp_path / "data", target_is_directory=True)
    with pytest.raises(ValueError):
        copy_resources(files, output)
    (output / "data").unlink()
    (output / "data").write_text("keep")
    with pytest.raises(ValueError):
        copy_resources(files, output)
    assert (output / "data").read_text() == "keep"


def test_generated_file_collision_and_output_nested_in_resources(tmp_path):
    source = notebook(tmp_path)
    (tmp_path / "start.sh").write_text("do not overwrite generated startup")
    with pytest.raises(ValueError, match="collides"):
        convert(source, tmp_path / "out", include=["start.sh"])
    assert "uvicorn" in (tmp_path / "out/start.sh").read_text()
    (tmp_path / "assets").mkdir()
    with pytest.raises(ValueError, match="inside included"):
        convert(source, tmp_path / "assets/out", include=["assets"])


@pytest.mark.parametrize(
    "tag", ["", "-option", "bad tag", "$(touch marker)", "a" * 256]
)
def test_invalid_image_tag_refused_before_generation(tmp_path, tag):
    with pytest.raises(ValueError, match="Image tag"):
        convert(notebook(tmp_path), tmp_path / "out", image_tag=tag)
    assert not (tmp_path / "out").exists()


def test_image_build_requires_docker_generation(tmp_path):
    with pytest.raises(ValueError, match="cannot be combined"):
        convert(
            notebook(tmp_path), tmp_path / "out", image_tag="example", skip_docker=True
        )


@pytest.mark.parametrize(
    "failure,message",
    [
        ("missing", "Docker CLI is required"),
        ("failed", "build failed"),
        ("no_id", "did not return"),
        ("bad_id", "invalid image"),
    ],
)
def test_build_failure_is_not_reported_as_success(
    tmp_path, monkeypatch, failure, message
):
    def docker(command, **kw):
        if failure == "missing":
            raise FileNotFoundError()
        if failure == "failed":
            raise subprocess.CalledProcessError(42, command)
        if failure == "bad_id":
            Path(command[5]).write_text("not an image")

    monkeypatch.setattr("apizr.legacy_delivery.subprocess.run", docker)
    with pytest.raises(RuntimeError, match=message):
        build_image(tmp_path, "example")


def test_cli_failure_has_nonzero_status(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "apizr.main.build_image",
        lambda *a: (_ for _ in ()).throw(RuntimeError("Docker failed")),
    )
    with pytest.raises(SystemExit, match="apizr: Docker failed"):
        main(
            [
                "--notebook",
                str(notebook(tmp_path)),
                "--output-dir",
                str(tmp_path / "out"),
                "--build-image",
                "example",
            ]
        )
    assert capsys.readouterr().out == ""
