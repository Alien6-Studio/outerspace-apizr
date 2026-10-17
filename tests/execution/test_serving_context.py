"""Worker capture suppression is bounded to worker execution, including failures."""

import os

import pytest

from apizr.execution import worker as single
from apizr.repository_execution import worker as repository


@pytest.mark.parametrize("worker", [single, repository])
@pytest.mark.parametrize("previous", [None, "caller-state", "1"])
@pytest.mark.parametrize("failure", [False, True])
def test_worker_restores_callers_serving_marker(monkeypatch, worker, previous, failure):
    if previous is None:
        monkeypatch.delenv("APIZR_SERVED_PROCESS", raising=False)
    else:
        monkeypatch.setenv("APIZR_SERVED_PROCESS", previous)

    def protocol():
        assert os.environ["APIZR_SERVED_PROCESS"] == "1"
        if failure:
            raise RuntimeError("worker failed")

    monkeypatch.setattr(worker, "_run_protocol", protocol)
    if failure:
        with pytest.raises(RuntimeError, match="worker failed"):
            worker.main()
    else:
        worker.main()
    assert os.environ.get("APIZR_SERVED_PROCESS") == previous
