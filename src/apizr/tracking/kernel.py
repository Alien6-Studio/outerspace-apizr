"""Bounded observations of an already-running kernel; no IPython imports or hooks."""

import builtins
from hashlib import sha256
from typing import Protocol, cast

from apizr.experiments import CellIdentity, EvidenceOrigin

MAX_CELL_BYTES = 1024 * 1024


class _Kernel(Protocol):
    def get_parent(self, channel: str = "shell") -> dict[str, object]: ...


class _DisplayHook(Protocol):
    prompt_count: int


class _Shell(Protocol):
    displayhook: _DisplayHook
    kernel: _Kernel


def current_cell() -> CellIdentity:
    """Read the current execute request through IPython's existing builtin.

    The frontend's optional cellId and raw request source are kernel observations,
    never identities of a saved notebook or its exported Python representation.
    """
    getter = vars(builtins).get("get_ipython")
    if not callable(getter):
        return CellIdentity()
    shell = cast(_Shell | None, getter())
    if shell is None or getattr(shell, "kernel", None) is None:
        return CellIdentity()
    parent = shell.kernel.get_parent("shell")
    if type(parent) is not dict:
        raise ValueError("tracking_kernel_observation_invalid")
    header = parent.get("header")
    if type(header) is not dict:
        return CellIdentity()
    if cast(dict[str, object], header).get("msg_type") != "execute_request":
        return CellIdentity()
    content = parent.get("content")
    metadata = parent.get("metadata", {})
    if type(content) is not dict or type(metadata) is not dict:
        raise ValueError("tracking_kernel_observation_invalid")
    source = cast(dict[str, object], content).get("code")
    if type(source) is not str or len(source) > MAX_CELL_BYTES:
        raise ValueError("tracking_kernel_observation_invalid")
    raw = source.encode("utf-8")
    if len(raw) > MAX_CELL_BYTES:
        raise ValueError("tracking_kernel_observation_invalid")
    # InteractiveShell advances its next-input counter before user code starts.
    # The public display prompt counter identifies the active execution instead.
    count = shell.displayhook.prompt_count
    if type(count) is not int or count < 0:
        raise ValueError("tracking_kernel_observation_invalid")
    return CellIdentity.model_validate(
        {
            "cell_id": cast(dict[str, object], metadata).get("cellId"),
            "execution_count": count or None,
            "source_digest": sha256(raw).hexdigest(),
            "origin": EvidenceOrigin.RUNTIME,
        }
    )
