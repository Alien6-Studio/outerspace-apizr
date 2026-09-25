"""Typed Python calls use the same bounded, cancellable worker as the CLI."""

import sys
from threading import Event
from typing import TypeVar

from pydantic import BaseModel

from apizr.extension_runtime import Limits, invoke_extension

from .model import (
    AttestRequest,
    DeliveryResult,
    DiscoverRequest,
    DiscoverResult,
    FetchRequest,
    FetchResult,
    PublishRequest,
    PublishResult,
    VerifyRequest,
)

T = TypeVar("T", bound=BaseModel)


def _invoke(operation, request, cancel, result_type: type[T]) -> T:
    response = invoke_extension(
        sys.executable,
        "apizr_attest.protocol",
        operation,
        request.model_dump(by_alias=True),
        environment={},
        cancel=cancel,
        limits=Limits(
            wall_time_ms=request.timeout_ms,
            max_stdout_bytes=131072 if operation == "discover" else 65536,
        ),
    )
    return result_type.model_validate(response.result)


def attest(request: AttestRequest, *, cancel: Event | None = None) -> DeliveryResult:
    return _invoke(
        "attest",
        AttestRequest.model_validate(request.model_dump(by_alias=True)),
        cancel,
        DeliveryResult,
    )


def verify(request: VerifyRequest, *, cancel: Event | None = None) -> DeliveryResult:
    return _invoke(
        "verify",
        VerifyRequest.model_validate(request.model_dump(by_alias=True)),
        cancel,
        DeliveryResult,
    )


def publish(request: PublishRequest, *, cancel: Event | None = None) -> PublishResult:
    return _invoke(
        "publish",
        PublishRequest.model_validate(request.model_dump(by_alias=True)),
        cancel,
        PublishResult,
    )


def discover(
    request: DiscoverRequest, *, cancel: Event | None = None
) -> DiscoverResult:
    return _invoke(
        "discover",
        DiscoverRequest.model_validate(request.model_dump(by_alias=True)),
        cancel,
        DiscoverResult,
    )


def fetch(request: FetchRequest, *, cancel: Event | None = None) -> FetchResult:
    return _invoke(
        "fetch",
        FetchRequest.model_validate(request.model_dump(by_alias=True)),
        cancel,
        FetchResult,
    )
