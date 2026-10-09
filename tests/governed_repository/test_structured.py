"""Actual OCI execution of the retained shared TypedDict object contract."""

import sys

import pytest
from structured_contracts.test_repository import FILES, PAYLOAD, SELECTED
from structured_contracts.test_runtime import INVALID_NESTED

from apizr.governed_repository.runtime import GovernedRuntime
from apizr.oci.model import ExecutionPolicyV2
from governed_repository.helpers import bundle


@pytest.mark.parametrize("interface", ["rest", "mcp"])
def test_real_oci_structured_payload_and_rejections(worker_image, tmp_path, interface):
    root = bundle(
        tmp_path / "oci",
        interface,
        files=FILES,
        selected=SELECTED,
        policy=ExecutionPolicyV2(),
        image=worker_image,
    )
    runtime = GovernedRuntime(root, interface)
    result = runtime.invoke(SELECTED[0], PAYLOAD)
    assert result.status == "success" and result.value == 6.0
    for invalid in INVALID_NESTED:
        assert (
            runtime.invoke(SELECTED[0], {"payload": invalid}).status == "invalid_input"
        )
    assert "typed" not in sys.modules
