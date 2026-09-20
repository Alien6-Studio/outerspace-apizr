import pytest

from apizr.execution.model import ExecutionResult
from apizr.oci import supervisor
from apizr.oci.provider import ContainerState, ProviderError

from .helpers import planned


class FakeProvider:
    identity = "apizr.docker-engine/v1"
    removed = False
    created = False
    failure = None
    oom = False

    def probe(self, runtime):
        if self.failure == "probe":
            raise ProviderError()

    def create(self, name, plan, root, environment):
        self.created = True
        assert (root / "original").read_bytes() == (
            root / plan.worker.executable_path
        ).read_bytes()
        if self.failure == "create":
            raise ProviderError()
        if self.failure == "filesystem":
            raise OSError("PRIVATE")

    def command(self, name):
        return ["fake"]

    def final_state(self, name, *, timeout=1.0):
        assert self.created and not self.removed
        return ContainerState(False, "exited", self.oom, 137 if self.oom else 23)

    def remove(self, name):
        self.removed = True
        if self.failure == "remove":
            raise ProviderError("cleanup_failed")


@pytest.mark.parametrize(
    "failure,status",
    [
        (None, "success"),
        ("probe", "backend_unavailable"),
        ("create", "backend_unavailable"),
        ("filesystem", "worker_failed"),
        ("remove", "cleanup_failed"),
        ("exchange", "worker_failed"),
        ("timeout", "timeout"),
        ("oom", "resource_limit"),
    ],
)
def test_all_lifecycle_paths_cleanup(monkeypatch, failure, status):
    provider = FakeProvider()
    provider.failure = failure
    provider.oom = failure == "oom"

    def exchange(*args, **kwargs):
        if failure == "exchange":
            raise OSError("PRIVATE")
        return ExecutionResult(
            status="timeout"
            if failure == "timeout"
            else "worker_failed"
            if failure == "oom"
            else "success",
            value=None,
        )

    monkeypatch.setattr(supervisor, "exchange", exchange)
    value, raw = planned()
    result = supervisor.execute(value, raw, {}, provider=provider)
    assert result.status == status
    assert provider.removed == provider.created
    assert "PRIVATE" not in result.model_dump_json()


def test_wrong_provider_and_default_provider(monkeypatch):
    value, raw = planned()
    provider = FakeProvider()
    provider.identity = "other"
    assert (
        supervisor.execute(value, raw, {}, provider=provider).status
        == "backend_unavailable"
    )
    provider.identity = "apizr.docker-engine/v1"
    provider.failure = "probe"
    monkeypatch.setattr(supervisor, "DockerProvider", lambda: provider)
    assert supervisor.execute(value, raw, {}).status == "backend_unavailable"


def test_notebook_executable_required():
    from apizr.capabilities import document_digest
    from apizr.capability_notebooks import inspect_notebook_bytes
    from apizr.inspection import Inspection
    from apizr.oci.model import ExecutionPolicyV2
    from apizr.oci.planner import plan
    from apizr.readiness import assess, report_digest

    from .helpers import IMAGE

    raw = b'{"cells":[{"cell_type":"code","id":"oci-example","execution_count":null,"metadata":{},"outputs":[],"source":["def f(): return 1"]}],"metadata":{},"nbformat":4,"nbformat_minor":5}'
    nb = inspect_notebook_bytes(raw, module_name="nb_sample")
    executable = nb.python_source.encode()
    readiness = assess(nb.document, executable)
    inspected = Inspection(
        capability_ir=nb.document,
        ir_digest=document_digest(nb.document),
        readiness=readiness,
        readiness_digest=report_digest(readiness),
    )
    runtime = plan(
        inspected, raw, "f", ExecutionPolicyV2(), IMAGE, executable=executable
    )
    assert supervisor.execute(runtime, raw, {}).status == "binding_failed"


@pytest.mark.parametrize(
    "status",
    [
        "success",
        "timeout",
        "source_mismatch",
        "binding_failed",
        "execution_failed",
        "output_limit",
        "result_invalid",
    ],
)
def test_only_generic_worker_failure_observes_terminal_state(monkeypatch, status):
    provider = FakeProvider()
    provider.oom = True

    def forbidden(*args, **kwargs):
        pytest.fail("Observation must not delay or reinterpret this result")

    provider.final_state = forbidden
    monkeypatch.setattr(
        supervisor, "exchange", lambda *a: ExecutionResult(status=status)
    )
    value, raw = planned()
    assert supervisor.execute(value, raw, {}, provider=provider).status == status
    assert provider.created and provider.removed


@pytest.mark.parametrize(
    "evidence,status",
    [
        (None, "worker_failed"),
        (ContainerState(False, "exited", False, 137), "worker_failed"),
        (ContainerState(False, "exited", False, 23), "worker_failed"),
        (ContainerState(True, "running", True, 137), "worker_failed"),
        (ContainerState(False, "exited", True, 137), "resource_limit"),
        (ProviderError(), "backend_unavailable"),
        (OSError("PRIVATE"), "worker_failed"),
    ],
)
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_observe_before_removal_and_cleanup_failure_has_precedence(
    monkeypatch, evidence, status, cleanup_fails
):
    provider = FakeProvider()
    events = []

    def observe(name, **kwargs):
        assert provider.created and not provider.removed
        events.append("observe")
        if isinstance(evidence, Exception):
            raise evidence
        return evidence

    def remove(name):
        events.append("remove")
        provider.removed = True
        if cleanup_fails:
            raise ProviderError("cleanup_failed")

    provider.final_state = observe
    provider.remove = remove
    monkeypatch.setattr(
        supervisor, "exchange", lambda *a: ExecutionResult(status="worker_failed")
    )
    value, raw = planned()
    result = supervisor.execute(value, raw, {}, provider=provider)
    assert result.status == ("cleanup_failed" if cleanup_fails else status)
    assert events == ["observe", "remove"] and provider.removed
    assert "PRIVATE" not in result.model_dump_json()
    assert set(result.model_dump()) == {"schema_version", "status", "value"}
