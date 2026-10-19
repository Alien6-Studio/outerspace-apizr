"""Served calls preserve business behavior without constructing SDK captures."""

import asyncio
import importlib
import inspect

import pytest

from apizr import tracking
from apizr.experiments.store import DEFAULT_STORE


@pytest.mark.parametrize("already_decorated", [False, True])
@pytest.mark.parametrize("asynchronous", [False, True])
def test_served_decorator_never_constructs_a_session(
    tmp_path, monkeypatch, already_decorated, asynchronous
):
    returned = object()

    def body(value: object) -> object:
        tracking.log_parameter("ignored", value)
        tracking.log_input("ignored", "missing.csv")
        tracking.log_metric("ignored", object())
        tracking.log_artifact("ignored", "missing.bin")
        return returned

    async def async_body(value: object) -> object:
        await asyncio.sleep(0)
        return body(value)

    original = async_body if asynchronous else body
    wrapped = (
        tracking.experiment(parameters=["value"], root=tmp_path)(original)
        if already_decorated
        else original
    )
    monkeypatch.setenv("APIZR_SERVED_PROCESS", "1")

    def forbidden(*args, **kwargs):
        raise AssertionError("served call constructed a capture or inspected arguments")

    module = importlib.import_module("apizr.tracking.decorator")
    monkeypatch.setattr(module, "session", forbidden)
    monkeypatch.setattr(module, "_argument", forbidden)
    if not already_decorated:
        monkeypatch.setattr(inspect, "signature", forbidden)
        wrapped = tracking.experiment(parameters=["value"], root=tmp_path)(original)
        assert wrapped is original
    else:
        assert inspect.signature(wrapped) == inspect.signature(original)
    value = object()
    assert (asyncio.run(wrapped(value)) if asynchronous else wrapped(value)) is returned
    assert not (tmp_path / DEFAULT_STORE).exists()


def test_served_exception_identity_and_explicit_session_suppression(
    tmp_path, monkeypatch
):
    failure = ValueError("original business failure")

    @tracking.experiment(root=tmp_path)
    def failing():
        raise failure

    monkeypatch.setenv("APIZR_SERVED_PROCESS", "1")
    with pytest.raises(ValueError) as caught:
        failing()
    assert caught.value is failure
    with tracking.session(root=tmp_path, source="missing.py") as capture:
        tracking.log_metric("ignored", object())
    assert capture.disabled and capture.record is None
    assert not (tmp_path / DEFAULT_STORE).exists()
