from execution import test_process as reviewed

from apizr.execution.policy import ExecutionPolicy
from apizr.repository_execution.supervisor import execute

from .helpers import planned


def test_ordinary_descendant_cleanup_reuses_79_regression(tmp_path, monkeypatch):
    def invoke(source, payload=None, **policy):
        plan, exposure, sources, _ = planned(
            source.replace("def f(", "def run("),
            policy=ExecutionPolicy.model_validate(policy),
        )
        return execute(plan, exposure, sources, payload or {})

    monkeypatch.setattr(reviewed, "invoke", invoke)
    reviewed.test_ordinary_descendant_is_stopped_with_worker(tmp_path)
