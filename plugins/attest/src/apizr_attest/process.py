"""Attest diagnostics over the shared bounded native-process runner."""

from pathlib import Path

from apizr_oci.model import BuildError
from apizr_oci.native import run as run_native

from .model import AttestError


def run(
    executable: Path, arguments: list[str], work: Path, deadline: float, limit: int
) -> bytes:
    try:
        return run_native(executable, arguments, work, deadline, limit)
    except BuildError as error:
        raise AttestError(str(error).replace("native_", "attest_", 1)) from None
