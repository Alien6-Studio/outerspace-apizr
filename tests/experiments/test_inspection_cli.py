"""CLI completion succeeds independently of scientific uncertainty or readiness."""

import json

import pytest

from apizr.cli import main
from apizr.environment.extras import MissingExtra

from .inspection_support import project, write_source


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_cli_success_and_exit_zero(tmp_path, capfd, format_name):
    source = project(tmp_path)
    assert main(["experiment", "inspect", str(source), "--format", format_name]) == 0
    out, err = capfd.readouterr()
    assert not err
    if format_name == "json":
        value = json.loads(out)
        assert value["states"]["randomness"] == "uncontrolled"
        assert value["serving"]["readiness"]["assessments"][0]["state"] == "conditional"
    else:
        assert "Experiment inspection" in out and "Serving — PARTIAL" in out


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["run"],
        ["inspect"],
        ["inspect", "x.py", "--format", "yaml"],
        ["inspect", "x.py", "--max-input-bytes", "word"],
    ],
)
def test_invocation_errors(arguments):
    with pytest.raises(SystemExit) as error:
        main(["experiment", *arguments])
    assert error.value.code == 2


@pytest.mark.parametrize(
    "failure", ["syntax", "missing", "limit", "input", "module", "extension"]
)
def test_fatal_redacted_errors(tmp_path, capfd, failure):
    source = write_source(tmp_path, "x = 1")
    options = []
    if failure == "syntax":
        source.write_text("private_source_sentinel =")
    elif failure == "missing":
        source.unlink()
    elif failure == "limit":
        options = ["--max-input-bytes", "0"]
    elif failure == "input":
        options = ["--input", "a=/private_source_sentinel"]
    elif failure == "module":
        options = ["--module-name", "/private_source_sentinel"]
    else:
        source = tmp_path / "unsupported.txt"
    assert main(["experiment", "inspect", str(source), *options]) == 2
    out, err = capfd.readouterr()
    assert not out
    assert "unable to inspect source" in err
    assert "private_source_sentinel" not in err and str(tmp_path) not in err


def test_missing_notebook_extra_is_actionable(tmp_path, monkeypatch, capfd):
    from apizr.experiments import inspection

    def missing(*args, **kwargs):
        raise MissingExtra("Install outerspace-apizr[notebook]")

    monkeypatch.setattr(inspection, "inspect_experiment", missing)
    assert main(["experiment", "inspect", str(tmp_path / "a.ipynb")]) == 2
    assert "outerspace-apizr[notebook]" in capfd.readouterr().err


def test_cli_explicit_root_and_input(tmp_path, capfd):
    path = write_source(tmp_path, "import pandas as pd\npd.read_csv(PATH)")
    (tmp_path / "data.csv").write_text("a\n1\n")
    assert (
        main(
            [
                "experiment",
                "inspect",
                str(path),
                "--root",
                str(tmp_path),
                "--input",
                "training=data.csv",
                "--module-name",
                "research.train",
                "--format",
                "json",
            ]
        )
        == 0
    )
    result = json.loads(capfd.readouterr().out)
    assert result["data"]["artifacts"][0]["origin"] == "declared"
    assert result["code"]["source"]["module"] == "research.train"
