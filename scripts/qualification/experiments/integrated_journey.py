"""Bind real Jupyter captures, CLI, installed VSIX and REST/MCP to the same Runs."""

import ast
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from scripts.qualification.experiments.experiment_jupyter_proof import Kernel
from scripts.qualification.experiments.qualify_data_science_journey import (
    EXAMPLE,
    ROOT,
    digest,
    network_guard,
    run,
    serving_checks,
    write,
)
from scripts.qualification.packaging.vscode_source import directory


def prepare_kernel(python, output):
    """Retain locked kernel wheels before the measured offline workload starts."""
    lock = output / "jupyter-requirements.lock"
    run(
        [
            "uv",
            "export",
            "--locked",
            "--only-group",
            "jupyter-qualification",
            "--no-emit-project",
            "--output-file",
            lock,
        ],
        cwd=ROOT,
    )
    wheels = output / "jupyter-wheels"
    (output / "jupyter-download.log").write_text(
        run(
            [
                python,
                "-m",
                "pip",
                "download",
                "--require-hashes",
                "--only-binary=:all:",
                "--dest",
                wheels,
                "-r",
                lock,
            ],
            cwd=output,
        )
    )
    (output / "jupyter-install.log").write_text(
        run(
            [
                python,
                "-m",
                "pip",
                "install",
                "--require-hashes",
                "--no-index",
                "--find-links",
                wheels,
                "-r",
                lock,
            ],
            cwd=output,
        )
    )
    write(
        output / "jupyter-wheels.json",
        [{"file": p.name, "sha256": digest(p)} for p in sorted(wheels.glob("*.whl"))],
    )


@contextmanager
def no_training(python, output):
    """Profile trusted serving Python processes; positively test the fit canary."""
    site = Path(
        run(
            [
                python,
                "-I",
                "-c",
                "import sysconfig; print(sysconfig.get_path('purelib'))",
            ],
            cwd=output,
        ).strip()
    )
    module = site / "qualification_no_training.py"
    hook = site / "qualification_no_training.pth"
    assert not module.exists() and not hook.exists()
    log = output / "training-events.jsonl"
    processes = output / "serving-processes.jsonl"
    module.write_text(
        "import json,os,sys\n"
        f"LOG={str(log)!r}\n"
        f"with open({str(processes)!r},'a') as stream: stream.write(json.dumps({{'pid':os.getpid()}})+'\\n')\n"
        "def observe(frame,event,arg):\n"
        "    if event == 'call' and (frame.f_code.co_name == 'train' and 'fraud_detection' in frame.f_code.co_filename or frame.f_code.co_name == 'fit' and 'sklearn' in frame.f_code.co_filename):\n"
        "        with open(LOG,'a') as stream: stream.write(json.dumps({'pid':os.getpid(),'function':frame.f_code.co_name})+'\\n')\n"
        "        raise RuntimeError('qualification_training_forbidden')\n"
        "sys.setprofile(observe)\n"
    )
    try:
        hook.write_text("import qualification_no_training\n")
        control = """import sys
namespace = {}
name, filename = sys.argv[1:]
exec(compile('def '+name+'(): pass', filename, 'exec'), namespace)
try: namespace[name]()
except RuntimeError as error: assert str(error) == 'qualification_training_forbidden'
else: raise AssertionError('training canary is inactive')
"""
        for name, filename in (
            ("fit", "sklearn/positive_control.py"),
            ("train", "fraud_detection.py"),
        ):
            run([python, "-I", "-c", control, name, filename], cwd=output)
        assert len(log.read_text().splitlines()) == 2
        log.write_text("")
        processes.write_text("")
        observation = {}
        yield observation
        assert log.read_bytes() == b"", "Serving executed training code"
        pids = {json.loads(line)["pid"] for line in processes.read_text().splitlines()}
        assert len(pids) >= 2, "Observe both real REST and MCP serving processes"
        observation.update(
            positive_controls=2, training_calls=0, serving_pids=sorted(pids)
        )
    finally:
        hook.unlink(missing_ok=True)
        module.unlink(missing_ok=True)
        for compiled in (site / "__pycache__").glob("qualification_no_training.*.pyc"):
            compiled.unlink()


def prove(python, wheels, target, output, *, vsix=None, code=None):
    """Use one installed engine, two successful cells and one real kernel error."""
    assert (vsix is None) == (code is None)
    output.mkdir(parents=True, exist_ok=False)
    python = python.absolute()
    origin = json.loads(
        run(
            [
                python,
                "-I",
                "-c",
                "import apizr,json,sys; from importlib.metadata import version; print(json.dumps({'module':apizr.__file__,'prefix':sys.prefix,'python':sys.version,'kernel':version('ipykernel')}))",
            ],
            cwd=output,
        )
    )
    assert Path(origin["module"]).is_relative_to(Path(origin["prefix"]))
    assert not Path(origin["module"]).is_relative_to(ROOT)
    project = output / "project"
    shutil.copytree(EXAMPLE, project)
    notebook = project / "fraud_detection.ipynb"
    source = "\n".join(
        "".join(c["source"])
        for c in json.loads(notebook.read_text())["cells"]
        if c["cell_type"] == "code"
    )
    # The explicit Python source anchors SDK evidence. Unsaved kernel text alone
    # cannot authorize notebook exposure; the production refusal remains intact.
    marker = 'Path("artifacts/trained.txt").write_text("Training completed.\\n")'
    assert marker in source
    source = source.replace(
        marker,
        'marker = Path("artifacts/trained.txt")\n    marker.write_text((marker.read_text() if marker.exists() else "") + "Training completed.\\n")',
    )
    (project / "fraud_detection.py").write_text(source)
    (project / "apizr.toml").write_text('schema_version = "apizr.project/v1"\n')
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "PYTHONPATH",
            "PYTHONHOME",
            "VIRTUAL_ENV",
            "APIZR_EXPERIMENT_RUNNER",
            "APIZR_SERVED_PROCESS",
        }
    }
    env.update(APIZR_TELEMETRY="0")

    def cli(*arguments, expected=0):
        result = subprocess.run(
            [
                str(python),
                "-I",
                "-B",
                "-m",
                "apizr.cli",
                "experiment",
                *map(str, arguments),
            ],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == expected, result.stdout + result.stderr
        return result

    cells = []
    executed = []

    def retain_cell(source, cell_id, reply, messages):
        outputs = []
        for message in messages:
            kind = message["msg_type"]
            if kind in {"stream", "error", "display_data", "execute_result"}:
                content = dict(message["content"])
                content.pop("transient", None)
                outputs.append({"output_type": kind, **content})
        executed.append(
            {
                "cell_type": "code",
                "id": cell_id,
                "metadata": {},
                "source": source,
                "execution_count": reply["execution_count"],
                "outputs": outputs,
            }
        )
        write(
            output / "executed.ipynb",
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {
                    "kernelspec": {
                        "display_name": "Python 3",
                        "language": "python",
                        "name": "python3",
                    }
                },
                "cells": executed,
            },
        )

    started = time.monotonic()
    kernel = Kernel(project, python=python)
    try:
        initialization = "from pathlib import Path\nimport sys\nsys.path.insert(0, str(Path.cwd()))\nfrom apizr import tracking\nfrom fraud_detection import train\nfrom sklearn.metrics import roc_auc_score"
        reply, messages = kernel.execute(initialization, "imports")
        retain_cell(initialization, "imports", reply, messages)
        for variant in ("a", "b"):
            shutil.copyfile(
                project / f"data/transactions-{variant}.csv",
                project / "data/transactions.csv",
            )
            cell = (
                """with tracking.session(root=Path.cwd(), source='fraud_detection.py', distributions=('joblib','scikit-learn','numpy','scipy')):
    tracking.log_parameter('cohort', %r)
    tracking.log_input('transactions', 'data/transactions.csv')
    truth, scores = train()
    tracking.log_metric('roc_auc', float(roc_auc_score(truth, scores)))
    tracking.log_artifact('model', 'artifacts/model.joblib')
"""
                % variant
            )
            reply, messages = kernel.execute(cell, "variant-" + variant)
            retain_cell(cell, "variant-" + variant, reply, messages)
            (output / ("variant-" + variant + ".cell.py")).write_text(cell)
            cells.append(
                {
                    "id": "variant-" + variant,
                    "status": reply["status"],
                    "execution_count": reply["execution_count"],
                }
            )
        failure = """with tracking.session(root=Path.cwd(), source='fraud_detection.py'):
    tracking.log_parameter('cohort', 'failure')
    raise RuntimeError('qualification_failed_cell')
"""
        reply, messages = kernel.finish(kernel.send(failure, "failed-cell"))
        retain_cell(failure, "failed-cell", reply, messages)
        assert reply["status"] == "error" and reply["ename"] == "RuntimeError"
        (output / "failure.cell.py").write_text(failure)
        cells.append(
            {
                "id": "failed-cell",
                "status": reply["status"],
                "execution_count": reply["execution_count"],
            }
        )
        write(output / "cells.json", cells)
    finally:
        kernel.close()
    run(
        [
            python,
            "-I",
            "-c",
            "import nbformat,sys; nbformat.validate(nbformat.read(sys.argv[1],as_version=4))",
            output / "executed.ipynb",
        ],
        cwd=output,
    )
    history = json.loads(cli("list", "--format", "json").stdout)
    assert len(history["runs"]) == 3
    records = {
        item["run_digest"]: json.loads(
            cli("show", item["run_digest"], "--format", "json").stdout
        )
        for item in history["runs"]
    }
    captured = {
        record["run"]["capture"]["cell"]["cell_id"]: (key, record)
        for key, record in records.items()
    }
    assert set(captured) == {"variant-a", "variant-b", "failed-cell"}
    for cell in cells:
        record = captured[cell["id"]][1]["run"]
        assert record["status"] == (
            "failed" if cell["status"] == "error" else "success"
        )
        assert record["capture"]["mode"] == "jupyter_cell"
        assert record["capture"]["cell"]["execution_count"] == cell["execution_count"]
    a, b = (captured["variant-" + name][0] for name in ("a", "b"))
    comparison = json.loads(cli("diff", a, b, "--format", "json").stdout)
    assert comparison["data"][0]["content_state"] == "changed"
    assert any(metric["state"] == "changed" for metric in comparison["metrics"])
    write(output / "history.json", history)
    write(output / "records.json", records)
    write(output / "diff.json", comparison)
    policy = output / "operator.json"
    write(
        policy,
        {
            "schema": "apizr.operator-policy/v1",
            "grants": [
                {
                    "adapter": "repository",
                    "operation": "analyze",
                    "target": {"kind": "local", "root": str(project)},
                    "permissions": ["source.analyze"],
                },
                {
                    "adapter": "experiments",
                    "operation": "history.read",
                    "target": {"kind": "local", "root": str(project)},
                    "store": ".apizr/experiments/v1",
                    "permissions": ["experiments.read"],
                },
            ],
        },
    )
    training = project / "artifacts/trained.txt"
    training_before = (training.read_bytes(), training.stat().st_mtime_ns)
    assert training_before[0] == b"Training completed.\n" * 2
    common = [
        "expose",
        b,
        "--root",
        project,
        "--operator-policy",
        policy,
        "--capability",
        "python:fraud_detection:predict",
        "--artifact",
        "model",
        "--dependency",
        "joblib",
        "--dependency",
        "scikit-learn",
        "--dependency-wheelhouse",
        wheels,
        "--allow-conditional",
    ]
    for interface in ("rest", "mcp"):
        exposure = json.loads(
            cli(
                *common,
                "--interface",
                interface,
                "--output-dir",
                output / "bundles" / interface,
                "--format",
                "json",
            ).stdout
        )
        assert exposure["binding"]["run_digest"] == b
        compiled = output / "bundles" / interface / "source/fraud_detection.py"
        tree = ast.parse(compiled.read_text())
        assert any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "predict"
            for node in ast.walk(tree)
        )
        assert not (compiled.parent / "artifacts/trained.txt").exists()
    model = project / "artifacts/model.joblib"
    original = model.read_bytes()
    try:
        model.write_bytes(original + b"tampered")
        result = cli(
            *common,
            "--interface",
            "rest",
            "--output-dir",
            output / "tampered",
            expected=2,
        )
        assert (
            "run_artifact_changed" in result.stderr
            and not (output / "tampered").exists()
        )
        (output / "tampered.log").write_text(result.stderr)
    finally:
        model.write_bytes(original)
    disabled = project / "disabled.json"
    write(disabled, {"schema_version": "apizr.provider-selection/v1", "providers": []})
    inspection = json.loads(
        cli(
            "inspect", "fraud_detection.py", "--providers", disabled, "--format", "json"
        ).stdout
    )
    assert not inspection["providers"]["active"]
    # History must also work when the producing implementation cannot be imported.
    unavailable = """import runpy,sys
class NoBuiltin:
    def find_spec(self,fullname,path=None,target=None):
        if fullname == 'apizr.scientific_providers.builtin' or fullname.startswith('apizr.scientific_providers.builtin.'):
            raise AssertionError('disabled provider was imported while reading history')
sys.meta_path.insert(0,NoBuiltin())
sys.argv=['apizr','experiment',*sys.argv[1:]]
runpy.run_module('apizr.cli',run_name='__main__')
"""
    for key, record in records.items():
        assert json.loads(cli("show", key, "--format", "json").stdout) == record
        assert (
            json.loads(
                run(
                    [
                        python,
                        "-I",
                        "-B",
                        "-c",
                        unavailable,
                        "show",
                        key,
                        "--format",
                        "json",
                    ],
                    cwd=project,
                    env=env,
                )
            )
            == record
        )
    assert json.loads(cli("diff", a, b, "--format", "json").stdout) == comparison
    serving = output / "serving/bin/python"
    run([sys.executable, "-m", "venv", serving.parent.parent], cwd=output)
    # Generated dependency locks include the exact science wheels. Install those
    # and transport dependencies from the already retained target export only.
    requirements = [
        value
        for interface in ("rest", "mcp")
        for name in ("requirements.txt", "application-requirements.txt")
        for value in ("-r", output / "bundles" / interface / name)
    ]
    (output / "serving-install.log").write_text(
        run(
            [
                serving,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                wheels,
                "--find-links",
                target / "extras",
                *requirements,
            ],
            cwd=output,
        )
    )
    network_guard(serving, output / "network.log")
    with no_training(serving, output) as observation:
        transport = serving_checks(python, serving, output / "bundles", output)
    assert training_before == (training.read_bytes(), training.stat().st_mtime_ns)
    editor = None
    if vsix is not None:
        from scripts.qualification.interfaces.vscode_proof import run_host

        write(
            output / "fixtures.json",
            {
                "python": str(python),
                "project": str(project),
                "policy": str(policy),
                "engine_origin": origin["module"],
                "outside_checkout": True,
                "history": history,
                "records": records,
                "diff": comparison,
                "comparison_ids": [a, b],
            },
        )
        args = SimpleNamespace(
            code=code,
            vsix=vsix,
            previous_vsix=None,
            untrusted=False,
            engine_executable=None,
        )
        editor = run_host(
            args,
            output,
            python,
            project,
            policy,
            tests=directory(ROOT) / "test/journey.cjs",
        )
    result = {
        "status": "passed",
        "runtime": origin,
        "runs": [
            {
                "run_digest": key,
                "status": record["run"]["status"],
                "cell": record["run"]["capture"]["cell"]["cell_id"],
            }
            for key, record in records.items()
        ],
        "cli_same_records": True,
        "provider_disabled_history": True,
        "provider_unavailable_history": True,
        "tampered_artifact": "run_artifact_changed",
        "transports": transport,
        "training_calls_during_serving": 0,
        "serving_training_observer": observation,
        "training_marker_unchanged": True,
        "elapsed_seconds": time.monotonic() - started,
        "editor": editor,
    }
    if vsix is not None:
        result["vsix"] = {"file": vsix.name, "sha256": digest(vsix)}
    write(output / "journey.json", result)
    return result
