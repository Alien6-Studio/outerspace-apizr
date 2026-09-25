"""Receipt operations over the existing extension protocol; no raw native diagnostics."""

import json
import sys
from pathlib import Path

from apizr_oci.model import BuildError

from apizr.extension_runtime.protocol import Request, unique_object
from apizr.local_plugins.models import PluginError

from .artifacts import execute_discover, execute_fetch, execute_publish
from .delivery import execute_attest, execute_verify
from .model import (
    AttestError,
    AttestRequest,
    DiscoverRequest,
    FetchRequest,
    PublishRequest,
    VerifyRequest,
)


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(1048577)
        if len(raw) > 1048576:
            raise ValueError()
        request = Request.model_validate(
            json.loads(raw, object_pairs_hook=unique_object)
        )
    except (ValueError, RecursionError):
        print("invalid_extension_request", file=sys.stderr)
        return 2
    response = {k: getattr(request, k) for k in ("protocol", "request_id", "operation")}
    try:
        if request.operation == "attest":
            result = execute_attest(
                AttestRequest.model_validate(request.arguments), Path.cwd()
            )
        elif request.operation == "verify":
            result = execute_verify(
                VerifyRequest.model_validate(request.arguments), Path.cwd()
            )
        elif request.operation == "publish":
            result = execute_publish(
                PublishRequest.model_validate(request.arguments), Path.cwd()
            )
        elif request.operation == "discover":
            result = execute_discover(
                DiscoverRequest.model_validate(request.arguments), Path.cwd()
            )
        elif request.operation == "fetch":
            result = execute_fetch(
                FetchRequest.model_validate(request.arguments), Path.cwd()
            )
        else:
            raise AttestError("unsupported_operation")
        response.update(status="ok", result=result.model_dump(by_alias=True))
    except (
        AttestError,
        PluginError,
        BuildError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RecursionError,
    ):
        response.update(
            status="error",
            error={
                "code": "delivery_refused",
                "message": "Delivery receipt operation refused or failed",
            },
        )
    print(json.dumps(response, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
