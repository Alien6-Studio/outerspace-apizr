"""Typed Python calls use the same bounded, cancellable worker as the CLI."""

import sys
from threading import Event

from apizr.extension_runtime import Limits, invoke_extension

from .model import AttestRequest, DeliveryResult, VerifyRequest


def _invoke(operation, request, cancel):
    response = invoke_extension(
        sys.executable,
        "apizr_attest.protocol",
        operation,
        request.model_dump(by_alias=True),
        environment={},
        cancel=cancel,
        limits=Limits(wall_time_ms=request.timeout_ms, max_stdout_bytes=65536),
    )
    return DeliveryResult.model_validate(response.result)


def attest(request: AttestRequest, *, cancel: Event | None = None) -> DeliveryResult:
    return _invoke(
        "attest",
        AttestRequest.model_validate(request.model_dump(by_alias=True)),
        cancel,
    )


def verify(request: VerifyRequest, *, cancel: Event | None = None) -> DeliveryResult:
    return _invoke(
        "verify",
        VerifyRequest.model_validate(request.model_dump(by_alias=True)),
        cancel,
    )
