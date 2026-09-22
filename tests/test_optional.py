import pytest

from apizr import optional
from apizr.cli import main
from apizr.modules.notebook_transformr.transformr.nbTransformr import NotebookTransformr


def test_missing_extra_is_actionable_without_installing(monkeypatch, capsys):
    monkeypatch.setattr(optional, "find_spec", lambda name: None)
    assert not optional.available("nbconvert")
    with pytest.raises(optional.MissingExtra, match=r"\[notebook\]"):
        NotebookTransformr()
    assert main(["--help"]) == 0
    assert "[legacy]" in capsys.readouterr().out
    assert main(["--script", "sample.py"]) == 2
    assert "[legacy]" in capsys.readouterr().err


def test_available_extra_does_not_modify_environment(monkeypatch):
    monkeypatch.setattr(optional, "find_spec", lambda name: object())
    assert optional.available("nbconvert", "black")
    assert optional.require("notebook", "nbconvert") is None
