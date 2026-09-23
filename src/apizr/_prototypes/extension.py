"""V04-01 one-shot trusted extension experiment, outside production dispatch."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from apizr.capabilities import document_digest, inspect_source

PROTOCOL = "apizr.extension-probe/v1"


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    protocol: Literal["apizr.extension-probe/v1"] = PROTOCOL
    request_id: Literal["packaging-proof"] = "packaging-proof"
    operation: Literal["describe"] = "describe"
    source_digest: str


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_digest: str
    message: Literal["demo extension reached"]


class Response(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    protocol: Literal["apizr.extension-probe/v1"]
    request_id: Literal["packaging-proof"]
    operation: Literal["describe"]
    result: Result


def validate_response(raw: str, request: Request) -> Response:
    response = Response.model_validate_json(raw)
    if response.result.source_digest != request.source_digest:
        raise ValueError("Extension result does not match the core source digest")
    return response


def invoke(python: Path, request: Request) -> Response:
    """Only the caller's explicitly supplied, reviewed executable is launched."""
    if not python.is_absolute() or not python.is_file():
        raise ValueError("An absolute installed extension Python path is required")
    try:
        completed = subprocess.run(
            [str(python), "-I", "-B", "-m", "apizr_extension_probe"],
            input=request.model_dump_json(),
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("Extension process failed or timed out") from error
    return validate_response(completed.stdout, request)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extension_python", type=Path)
    args = parser.parse_args()
    # The installed core produces the canonical artifact; the extension cannot
    # redefine it. No source repository, application import or dependency install.
    ir = inspect_source(
        b"def echo(value: str) -> str: return value\n", module_name="demo"
    )
    request = Request(source_digest=document_digest(ir).value)
    try:
        response = invoke(args.extension_python, request)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(response.model_dump(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
