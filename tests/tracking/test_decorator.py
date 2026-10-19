"""One Run per call, explicit parameter selection and preserved function behavior."""

import asyncio
import inspect

import pytest

from apizr import tracking
from apizr.experiments import EvidenceOrigin
from apizr.experiments.store import DEFAULT_STORE, records


def test_signature_metadata_return_identity_and_explicit_selection(tmp_path):
    returned = object()

    def function(rate: float, secret="never-record", *, epochs: int = 3) -> object:
        """Original documentation."""
        tracking.log_metric("score", 0.75)
        return returned

    wrapped = tracking.experiment(parameters=["rate", "epochs"], root=tmp_path)(
        function
    )
    assert inspect.signature(wrapped) == inspect.signature(function)
    assert wrapped.__name__ == function.__name__
    assert wrapped.__doc__ == function.__doc__
    assert wrapped.__annotations__ == function.__annotations__
    assert wrapped(0.1) is returned
    assert wrapped(0.2, secret="private") is returned
    found = list(records(tmp_path / DEFAULT_STORE))
    assert len(found) == 2
    assert sorted(r.run.call_parameters[1].value for r in found) == [0.1, 0.2]
    assert all(
        tuple(p.name for p in r.run.call_parameters) == ("epochs", "rate")
        for r in found
    )
    assert all(
        r.run.capture.function.qualified_name == function.__qualname__ for r in found
    )
    assert len({r.run.capture.function.definition_id for r in found}) == 1
    assert len({r.run.execution_id for r in found}) == 2
    assert all(
        "never-record" not in r.model_dump_json()
        and "private" not in r.model_dump_json()
        for r in found
    )


@pytest.mark.parametrize(
    "parameters,error",
    [
        (["missing"], "unknown"),
        (["x", "x"], "duplicate"),
        ("x", "invalid"),
        ([object()], "invalid"),
    ],
)
def test_bad_selection_is_refused_at_decoration_time_without_store(
    tmp_path, parameters, error
):
    with pytest.raises(
        tracking.TrackingError, match="tracking_parameter_selection_" + error
    ):
        tracking.experiment(parameters=parameters, root=tmp_path)(lambda x: x)
    assert not (tmp_path / DEFAULT_STORE).exists()


def test_objects_are_not_serialized_or_inspected(tmp_path):
    class ScientificObject:
        def __repr__(self):
            raise AssertionError("object repr")

        def __getattribute__(self, name):
            raise AssertionError("object attribute")

        def __reduce__(self):
            raise AssertionError("object pickle")

    value = ScientificObject()
    wrapped = tracking.experiment(parameters=["model"], root=tmp_path)(
        lambda model: model
    )
    assert wrapped(value) is value
    record = next(records(tmp_path / DEFAULT_STORE))
    parameter = record.run.call_parameters[0]
    assert parameter.origin == EvidenceOrigin.UNKNOWN and parameter.value is None
    assert parameter.value_type.endswith("ScientificObject")


def test_custom_metaclass_is_not_inspected(tmp_path):
    class Meta(type):
        def __getattribute__(self, name):
            raise AssertionError("metaclass attribute")

    class Value(metaclass=Meta):
        pass

    value = Value()
    wrapped = tracking.experiment(parameters=["x"], root=tmp_path)(lambda x: x)
    assert wrapped(value) is value
    record = next(records(tmp_path / DEFAULT_STORE))
    assert record.run.call_parameters[0].origin == EvidenceOrigin.UNKNOWN
    assert record.run.call_parameters[0].value_type is None


def test_business_exception_is_returned_unchanged_and_recorded(tmp_path):
    exception = ValueError("business-secret")

    @tracking.experiment(root=tmp_path)
    def function():
        raise exception

    with pytest.raises(ValueError) as caught:
        function()
    assert caught.value is exception
    record = next(records(tmp_path / DEFAULT_STORE))
    assert record.run.status == "failed"
    assert "business-secret" not in record.model_dump_json()


def test_invalid_call_preserves_original_type_error(tmp_path):
    def function(x):
        return x

    wrapped = tracking.experiment(parameters=["x"], root=tmp_path)(function)
    with pytest.raises(TypeError) as original:
        function()
    with pytest.raises(TypeError) as actual:
        wrapped()
    assert str(actual.value) == str(original.value)
    record = next(records(tmp_path / DEFAULT_STORE))
    assert record.run.status == "failed"
    assert record.run.call_parameters[0].origin == EvidenceOrigin.UNKNOWN


def test_async_capture_encloses_execution_and_preserves_result(tmp_path):
    returned = object()

    @tracking.experiment(parameters=["x"], root=tmp_path)
    async def function(x):
        await asyncio.sleep(0)
        tracking.log_metric("value", x)
        return returned

    assert inspect.iscoroutinefunction(function)

    async def run():
        return await asyncio.gather(function(1), function(2))

    assert asyncio.run(run()) == [returned, returned]
    found = list(records(tmp_path / DEFAULT_STORE))
    assert len(found) == 2
    assert sorted(r.run.metrics[0].value for r in found) == [1, 2]


def test_decorated_nested_call_obeys_session_refusal(tmp_path):
    @tracking.experiment(root=tmp_path)
    def function():
        raise AssertionError("business function must not execute")

    with tracking.session(root=tmp_path) as parent:
        with pytest.raises(tracking.TrackingError, match="tracking_nested_session"):
            function()
    assert parent.record.run.status == "failed"
    assert len(list(records(tmp_path / DEFAULT_STORE))) == 1


def test_decoration_is_inert_and_redefinitions_have_distinct_binding_ids(tmp_path):
    def function(x):
        return x

    first = tracking.experiment(parameters=["x"], root=tmp_path)(function)
    second = tracking.experiment(parameters=["x"], root=tmp_path)(function)
    assert not (tmp_path / DEFAULT_STORE).exists()
    first(1)
    second(1)
    assert (
        len(
            {
                r.run.capture.function.definition_id
                for r in records(tmp_path / DEFAULT_STORE)
            }
        )
        == 2
    )


def test_generator_lifecycle_is_explicitly_refused(tmp_path):
    def values():
        yield 1

    with pytest.raises(tracking.TrackingError, match="tracking_generator_unsupported"):
        tracking.experiment(root=tmp_path)(values)


def test_bare_decorator_uses_the_same_lifecycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    @tracking.experiment
    def function() -> int:
        return 7

    assert function() == 7
    assert next(records(tmp_path / DEFAULT_STORE)).run.status == "success"
