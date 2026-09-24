"""One versioned extension request. All build logs stay off protocol stdout."""

import json
import sys
from pathlib import Path

from apizr.extension_runtime.protocol import Request, unique_object

from .build import build
from .model import BuildError, BuildRequest


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
    response = {
        key: getattr(request, key) for key in ("protocol", "request_id", "operation")
    }
    try:
        if request.operation != "build":
            raise BuildError("unsupported_operation")
        arguments = BuildRequest.model_validate(request.arguments)
        result = build(arguments, workspace=Path.cwd())
        response.update(status="ok", result=result.model_dump(by_alias=True))
    except (BuildError, ValueError):
        # The core deliberately redacts remote errors; never print raw Docker logs.
        response.update(
            status="error",
            error={
                "code": "oci_build_failed",
                "message": "OCI service build refused or failed; daemon state is not confirmed on interruption",
            },
        )
    print(json.dumps(response, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
