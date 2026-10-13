"""Explicit call-parameter selection over the same context-local session lifecycle."""

import inspect
import uuid
from collections.abc import Callable, Sequence
from functools import wraps
from importlib.metadata import version
from pathlib import Path
from typing import ParamSpec, TypeVar, cast, overload

from apizr.experiments import (
    CallParameter,
    CaptureIdentity,
    CaptureMode,
    EvidenceOrigin,
    FunctionBinding,
)
from apizr.tracking.session import TrackingError, session

P = ParamSpec("P")
R = TypeVar("R")


def _argument(name: str, value: object) -> CallParameter:
    try:
        return CallParameter.model_validate(
            {"name": name, "value": value, "origin": EvidenceOrigin.RUNTIME}
        )
    except (ValueError, UnicodeError):
        # Read class metadata directly, never repr(), attributes or serializers
        # on the selected object. Scientific objects remain unknown JSON values.
        kind = type(value)
        if type(kind) is not type:
            return CallParameter(name=name, value=None, origin=EvidenceOrigin.UNKNOWN)
        module = type.__getattribute__(kind, "__module__")
        qualified = type.__getattribute__(kind, "__qualname__")
        if type(module) is not str or type(qualified) is not str:
            return CallParameter(name=name, value=None, origin=EvidenceOrigin.UNKNOWN)
        label = module + "." + qualified
        try:
            return CallParameter(
                name=name, value=None, value_type=label, origin=EvidenceOrigin.UNKNOWN
            )
        except (ValueError, UnicodeError):
            return CallParameter(name=name, value=None, origin=EvidenceOrigin.UNKNOWN)


@overload
def experiment(
    function: Callable[P, R],
    *,
    parameters: Sequence[str] = (),
    root: Path | None = None,
    store: Path | None = None,
    source: str | None = None,
    distributions: tuple[str, ...] = (),
    max_file_bytes: int = 1024**3,
) -> Callable[P, R]: ...


@overload
def experiment(
    function: None = None,
    *,
    parameters: Sequence[str] = (),
    root: Path | None = None,
    store: Path | None = None,
    source: str | None = None,
    distributions: tuple[str, ...] = (),
    max_file_bytes: int = 1024**3,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def experiment(
    function: Callable[P, R] | None = None,
    *,
    parameters: Sequence[str] = (),
    root: Path | None = None,
    store: Path | None = None,
    source: str | None = None,
    distributions: tuple[str, ...] = (),
    max_file_bytes: int = 1024**3,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate one ordinary or async function; imports never start a capture."""
    if (
        type(parameters) not in (tuple, list)
        or len(parameters) > 256
        or any(type(name) is not str for name in parameters)
    ):
        raise TrackingError("tracking_parameter_selection_invalid")
    names = tuple(sorted(parameters))
    if len(names) != len(set(names)):
        raise TrackingError("tracking_parameter_selection_duplicate")

    def decorate(function: Callable[P, R]) -> Callable[P, R]:
        signature = inspect.signature(function)
        if any(name not in signature.parameters for name in names):
            raise TrackingError("tracking_parameter_selection_unknown")
        if inspect.isgeneratorfunction(function) or inspect.isasyncgenfunction(
            function
        ):
            raise TrackingError("tracking_generator_unsupported")
        definition = FunctionBinding(
            module=function.__module__,
            qualified_name=function.__qualname__,
            definition_id=uuid.uuid4().hex,
            origin=EvidenceOrigin.RUNTIME,
        )

        def selected(
            args: tuple[object, ...], kwargs: dict[str, object]
        ) -> tuple[CallParameter, ...]:
            try:
                bound = signature.bind(*args, **kwargs)
                bound.apply_defaults()
            except TypeError:
                # Let the original call produce its own TypeError, inside a failed
                # capture. Do not substitute inspect.Signature's exception text.
                return tuple(
                    CallParameter(name=name, value=None, origin=EvidenceOrigin.UNKNOWN)
                    for name in names
                )
            return tuple(_argument(name, bound.arguments[name]) for name in names)

        def capture(arguments: tuple[CallParameter, ...]):
            return session(
                root=root,
                store=store,
                source=source,
                distributions=distributions,
                max_file_bytes=max_file_bytes,
                capture=CaptureIdentity(
                    mode=CaptureMode.DECORATED_CALL,
                    producer="apizr.tracking",
                    producer_version=version("outerspace-apizr"),
                    function=definition,
                    selected_parameters=names,
                ),
                call_parameters=arguments,
            )

        if inspect.iscoroutinefunction(function):

            @wraps(function)
            async def async_call(*args: P.args, **kwargs: P.kwargs):
                with capture(selected(args, kwargs)):
                    return await function(*args, **kwargs)

            return cast(Callable[P, R], async_call)

        @wraps(function)
        def call(*args: P.args, **kwargs: P.kwargs) -> R:
            with capture(selected(args, kwargs)):
                return function(*args, **kwargs)

        return call

    return decorate(function) if function is not None else decorate
