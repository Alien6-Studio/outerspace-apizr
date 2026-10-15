"""Qualify SDK capture in real kernels from an installed candidate outside checkout."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from importlib.metadata import version
from pathlib import Path
from typing import cast

from jupyter_client.manager import KernelManager

from apizr.experiments import CaptureMode, EvidenceOrigin
from apizr.experiments.store import DEFAULT_STORE, RunRecordV2, records


class Kernel:
    def __init__(self, root):
        self.root = root
        self.manager = KernelManager(connection_file=str(root / "connection.json"))
        spec = self.manager.kernel_spec
        assert spec is not None
        spec.argv = [
            sys.executable,
            "-I",
            "-B",
            "-m",
            "ipykernel_launcher",
            "-f",
            "{connection_file}",
        ]
        env = dict(os.environ)
        for name in ("APIZR_EXPERIMENT_RUNNER", "APIZR_SERVED_PROCESS"):
            env.pop(name, None)
        for name in ("IPYTHONDIR", "JUPYTER_CONFIG_DIR", "JUPYTER_RUNTIME_DIR"):
            path = root / name.lower()
            path.mkdir()
            env[name] = str(path)
        self.manager.start_kernel(cwd=str(root), env=env)
        self.client = self.manager.blocking_client()
        self.client.start_channels()
        self.client.wait_for_ready(timeout=30)

    def send(self, source, cell_id=None):
        message = self.client.session.msg(
            "execute_request",
            content={
                "code": source,
                "silent": False,
                "store_history": True,
                "user_expressions": {},
                "allow_stdin": False,
                "stop_on_error": True,
            },
            metadata={} if cell_id is None else {"cellId": cell_id},
        )
        self.client.shell_channel.send(message)
        return message["header"]["msg_id"]

    def finish(self, request, messages=None):
        observed = [] if messages is None else list(messages)
        deadline = time.monotonic() + 30
        while True:
            message = self.client.get_iopub_msg(
                timeout=max(0.1, deadline - time.monotonic())
            )
            if message.get("parent_header", {}).get("msg_id") != request:
                continue
            observed.append(message)
            if (
                message["msg_type"] == "status"
                and message["content"]["execution_state"] == "idle"
            ):
                break
        while True:
            reply = self.client.get_shell_msg(
                timeout=max(0.1, deadline - time.monotonic())
            )
            if reply.get("parent_header", {}).get("msg_id") == request:
                return reply["content"], observed

    def execute(self, source, cell_id=None):
        reply, messages = self.finish(self.send(source, cell_id))
        assert reply["status"] == "ok", reply
        return reply, messages

    def close(self):
        self.client.stop_channels()
        self.manager.shutdown_kernel(now=True)


def found(kernel) -> list[RunRecordV2]:
    observed = list(records(kernel.root / DEFAULT_STORE))
    assert all(isinstance(record, RunRecordV2) for record in observed)
    return cast(list[RunRecordV2], observed)


def prove_reexecution_unsaved_cells_and_display_are_preserved(kernel):
    kernel.execute(
        "from pathlib import Path\nfrom apizr import tracking\nprepared = tracking.session(root=Path.cwd())"
    )
    assert not (kernel.root / DEFAULT_STORE).exists()
    source = """import sys
from IPython.display import display, update_display
original_display = display
with prepared as capture:
    print("visible-stdout")
    print("visible-stderr", file=sys.stderr)
    display({"image/svg+xml": "<svg xmlns='http://www.w3.org/2000/svg'></svg>"}, raw=True, display_id="visible-display")
    update_display({"text/html": "<b>updated display</b>"}, raw=True, display_id="visible-display")
    tracking.log_input("in-memory")
    tracking.log_metric("score", 0.75)
assert display is original_display
"""
    reply, messages = kernel.execute(source, "session-cell")
    record = found(kernel)[0]
    assert record.run.capture.mode == CaptureMode.JUPYTER_CELL
    assert record.run.capture.cell.execution_count == reply["execution_count"]
    assert record.run.capture.cell.cell_id == "session-cell"
    assert (
        record.run.capture.cell.source_digest
        == hashlib.sha256(source.encode()).hexdigest()
    )
    assert record.run.subject.identity is None
    assert record.run.observed_inputs[0].origin == EvidenceOrigin.UNKNOWN
    assert {m["content"]["name"] for m in messages if m["msg_type"] == "stream"} == {
        "stdout",
        "stderr",
    }
    assert any(
        m["msg_type"] == "display_data" and "image/svg+xml" in m["content"]["data"]
        for m in messages
    )
    assert any(
        m["msg_type"] == "update_display_data"
        and m["content"]["transient"]["display_id"] == "visible-display"
        for m in messages
    )
    assert "visible-stdout" not in record.model_dump_json()
    source = (
        "with tracking.session(root=Path.cwd()):\n    tracking.log_metric('score', 0.8)"
    )
    first, _ = kernel.execute(source, "reexecuted-cell")
    second, _ = kernel.execute(source, "reexecuted-cell")
    repeated = [
        r for r in found(kernel) if r.run.capture.cell.cell_id == "reexecuted-cell"
    ]
    assert len(repeated) == 2
    assert {r.run.capture.cell.execution_count for r in repeated} == {
        first["execution_count"],
        second["execution_count"],
    }
    assert len({r.run.execution_id for r in repeated}) == 2


def prove_decorator_rebinding_and_unknown_scientific_values(kernel):
    definition = """from pathlib import Path
from apizr import tracking
class MemoryObject:
    def __repr__(self): raise AssertionError("do not represent the object")
    def __reduce__(self): raise AssertionError("do not pickle the object")
memory = MemoryObject()
@tracking.experiment(parameters=["rate", "model"], root=Path.cwd())
def fit(rate, model):
    tracking.log_metric("score", rate)
    return model
"""
    kernel.execute(definition, "definition-cell")
    assert not (kernel.root / DEFAULT_STORE).exists()
    for rate in (0.1, 0.2):
        kernel.execute(f"assert fit({rate}, memory) is memory", "call-cell")
    previous = found(kernel)
    assert len(previous) == 2
    assert len({r.run.capture.function.definition_id for r in previous}) == 1
    assert all(r.run.capture.mode == CaptureMode.DECORATED_CALL for r in previous)
    assert all(r.run.capture.cell.cell_id == "call-cell" for r in previous)
    assert all(
        r.run.call_parameters[0].origin == EvidenceOrigin.UNKNOWN for r in previous
    )
    kernel.execute(definition, "definition-cell")
    kernel.execute("assert fit(0.3, memory) is memory")
    current = found(kernel)
    assert len(current) == 3
    assert len({r.run.capture.function.definition_id for r in current}) == 2
    missing_id = next(r for r in current if r.run.capture.cell.cell_id is None)
    assert missing_id.run.capture.cell.source_digest is not None


def prove_interrupt_publishes_cancelled_run_and_remains_usable(kernel):
    source = """import time
from pathlib import Path
from apizr import tracking
with tracking.session(root=Path.cwd()):
    print("ready-for-interrupt", flush=True)
    time.sleep(30)
"""
    request = kernel.send(source, "interrupted-cell")
    messages = []
    deadline = time.monotonic() + 30
    while True:
        message = kernel.client.get_iopub_msg(
            timeout=max(0.1, deadline - time.monotonic())
        )
        if message.get("parent_header", {}).get("msg_id") != request:
            continue
        messages.append(message)
        if (
            message["msg_type"] == "stream"
            and "ready-for-interrupt" in message["content"]["text"]
        ):
            break
    kernel.manager.interrupt_kernel()
    reply, _ = kernel.finish(request, messages)
    assert reply["status"] == "error" and reply["ename"] == "KeyboardInterrupt"
    cancelled = found(kernel)[0]
    assert cancelled.run.status == "cancelled"
    assert cancelled.run.diagnostics[0].code == "tracking_cancelled"
    kernel.execute(
        "assert tracking.TrackingSession.current() is None\nwith tracking.session(root=Path.cwd()):\n    tracking.log_metric('recovered', 1)",
        "recovered-cell",
    )
    assert {r.run.status for r in found(kernel)} == {"cancelled", "success"}


def prove_example(kernel, notebook):
    document = json.loads(notebook.read_text())
    for cell in document["cells"]:
        if cell["cell_type"] == "code":
            kernel.execute("".join(cell["source"]), cell["id"])
    observed = found(kernel)
    assert len(observed) == 3 and all(r.run.status == "success" for r in observed)
    assert all(r.run.subject.identity is None for r in observed)
    assert all(
        item.origin == EvidenceOrigin.UNKNOWN
        for record in observed
        for item in record.run.observed_inputs
    )


def prove(output, notebook):
    import apizr

    proof = {
        "python": sys.version,
        "versions": {
            name: version(name)
            for name in ("outerspace-apizr", "ipykernel", "ipython", "jupyter-client")
        },
        "sdk_path": str(Path(apizr.__file__).resolve()),
        "cases": {},
    }
    with tempfile.TemporaryDirectory(
        prefix="apizr-jupyter-cases-", dir=output.parent
    ) as directory:
        for case in (
            prove_reexecution_unsaved_cells_and_display_are_preserved,
            prove_decorator_rebinding_and_unknown_scientific_values,
            prove_interrupt_publishes_cancelled_run_and_remains_usable,
        ):
            root = Path(directory) / case.__name__
            root.mkdir()
            kernel = Kernel(root)
            try:
                case(kernel)
                proof["cases"][case.__name__] = [
                    record.model_dump(mode="json") for record in found(kernel)
                ]
            finally:
                kernel.close()
        root = Path(directory) / "documented-example"
        root.mkdir()
        kernel = Kernel(root)
        try:
            prove_example(kernel, notebook)
            proof["cases"]["documented_example"] = [
                record.model_dump(mode="json") for record in found(kernel)
            ]
        finally:
            kernel.close()
    proof["example_sha256"] = hashlib.sha256(notebook.read_bytes()).hexdigest()
    proof["result"] = "pass"
    output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, nargs="?")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--example", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--installed", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.installed:
        assert args.example is not None
        prove(output, args.example)
        return
    if args.wheel is None:
        parser.error("A retained candidate wheel is required")
    wheel = args.wheel.resolve()
    checkout = Path(__file__).resolve().parents[3]
    with tempfile.TemporaryDirectory(prefix="apizr-jupyter-install-") as directory:
        root = Path(directory).resolve()
        environment = root / "env"
        lock = root / "requirements.lock"
        subprocess.run(
            [
                "uv",
                "export",
                "--locked",
                "--no-default-groups",
                "--group",
                "jupyter-qualification",
                "--no-emit-project",
                "--output-file",
                str(lock),
            ],
            cwd=checkout,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            ["uv", "venv", "--python", sys.executable, str(environment)], check=True
        )
        python = environment / "bin" / "python"
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--require-hashes",
                "--only-binary",
                ":all:",
                "-r",
                str(lock),
            ],
            check=True,
        )
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--no-deps",
                "--no-index",
                str(wheel),
            ],
            check=True,
        )
        driver = root / "driver.py"
        shutil.copyfile(__file__, driver)
        notebook = root / "jupyter-capture.ipynb"
        shutil.copyfile(checkout / "examples/tracking/jupyter-capture.ipynb", notebook)
        subprocess.run(
            [
                str(python),
                "-I",
                "-B",
                str(driver),
                "--installed",
                "--output",
                str(output),
                "--example",
                str(notebook),
            ],
            cwd=root,
            check=True,
            timeout=120,
        )
        proof = json.loads(output.read_text())
        assert Path(proof["sdk_path"]).is_relative_to(environment)
        assert not Path(proof["sdk_path"]).is_relative_to(checkout)
        proof["outside_checkout"] = True
        proof["candidate_wheel"] = wheel.name
        proof["candidate_sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
        proof["kernel_requirements_sha256"] = hashlib.sha256(
            lock.read_bytes()
        ).hexdigest()
        shutil.copyfile(lock, output.with_suffix(".requirements.lock"))
        output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
        print(
            json.dumps(
                {
                    "result": proof["result"],
                    "versions": proof["versions"],
                    "cases": len(proof["cases"]),
                    "outside_checkout": True,
                }
            )
        )


if __name__ == "__main__":
    main()
