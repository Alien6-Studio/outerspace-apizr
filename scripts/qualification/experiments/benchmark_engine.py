"""Measure engine costs on deterministic fixtures; timings are informational."""

import argparse
import cProfile
import hashlib
import json
import os
import platform
import pstats
import shutil
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]


def measure(operation: Callable[[], object], repeats: int) -> dict[str, Any]:
    samples = []
    outcomes = []
    for _ in range(repeats):
        start = time.perf_counter()
        try:
            operation()
            outcome = "success"
        except ValueError as error:
            if str(error) != "store_limit":
                raise
            outcome = "store_limit"
        samples.append(time.perf_counter() - start)
        outcomes.append(outcome)
    if len(set(outcomes)) != 1:
        raise ValueError("benchmark_outcome_unstable")
    return {
        "seconds": samples,
        "median_seconds": statistics.median(samples),
        "minimum_seconds": min(samples),
        "maximum_seconds": max(samples),
        "outcome": outcomes[0],
    }


def command(arguments: list[str], *, stdin: bytes | None = None) -> bytes:
    result = subprocess.run(
        [sys.executable, "-I", "-B", *arguments],
        cwd=ROOT,
        input=stdin,
        capture_output=True,
        check=False,
        timeout=120,
    )
    if result.returncode:
        raise RuntimeError(
            f"Benchmark command failed ({result.returncode}): {arguments!r}\n"
            + result.stderr.decode("utf-8", errors="replace")
        )
    return result.stdout


def cold_session(source: Path, root: Path) -> None:
    """Include import plus first capture, rather than crediting deferred work as saved.

    A recorded checkout may be selected for a same-interpreter before/after
    comparison. The child verifies that both SDK and value admission came from
    that checkout; all dependencies still come from this locked interpreter.
    """
    command(
        [
            "-c",
            "import sys; from pathlib import Path; "
            "source=Path(sys.argv[1]).resolve(); sys.path.insert(0,str(source)); "
            "import apizr.tracking as tracking; "
            "assert Path(tracking.__file__).resolve().is_relative_to(source); "
            "capture=tracking.session(root=Path(sys.argv[2])); "
            "capture.__enter__(); capture.__exit__(None,None,None); "
            "from apizr.experiments import values; "
            "assert Path(values.__file__).resolve().is_relative_to(source); "
            "assert capture.record is not None",
            str(source),
            str(root),
        ]
    )


def make_history(path: Path, count: int) -> tuple[str, str]:
    """Prepare canonical synthetic fixtures, outside the measured operations.

    Direct fixture writes avoid quadratic publication cost while constructing
    10,000 entries. The real durable publication path is measured separately.
    No production bounds or validators are patched, including for 10,000 Runs.
    """
    from apizr.experiments.model import EvidenceOrigin, ExperimentRun, Metric
    from apizr.experiments.serialization import (
        plan_bytes,
        read_plan,
        read_run,
        run_bytes,
    )

    fixture = ROOT / "tests/fixtures/experiments/v1"
    plan = read_plan((fixture / "plan.json").read_bytes())
    original = read_run((fixture / "run.json").read_bytes())
    planned = plan_bytes(plan)
    plans, runs = path / "plans", path / "runs"
    plans.mkdir(parents=True)
    runs.mkdir()
    (plans / (hashlib.sha256(planned).hexdigest() + ".json")).write_bytes(planned)
    identities = []
    for number in range(count):
        run = ExperimentRun.model_validate(
            original.model_dump()
            | {
                "metrics": (
                    Metric(name="sample", value=number, origin=EvidenceOrigin.RUNTIME),
                )
            }
        )
        raw = run_bytes(run)
        digest = hashlib.sha256(raw).hexdigest()
        (runs / (digest + ".json")).write_bytes(raw)
        identities.append(digest)
    return identities[0], identities[-1]


def profile(operation: Callable[[], object], path: Path) -> dict[str, int]:
    profiler = cProfile.Profile()
    profiler.runcall(operation)
    profiler.dump_stats(str(path))
    stats = pstats.Stats(profiler)
    with path.with_suffix(".txt").open("w") as output:
        pstats.Stats(profiler, stream=output).strip_dirs().sort_stats(
            "cumulative"
        ).print_stats(50)
    readable = path.with_suffix(".txt")
    readable.write_text(readable.read_text().rstrip() + "\n")
    # Record actual Python entry counts, not estimates from wall-clock timings.
    # Preserve per-location identities: get_stats_profile merges equal function
    # names (including distinct encode functions). Typeshed omits this mapping.
    calls: dict[tuple[str, int, str], tuple[int, int, float, float, dict]] = vars(
        stats
    )["stats"]
    return {
        f"{Path(filename).name}:{name}": values[1]
        for (filename, _line, name), values in calls.items()
        if Path(filename).name
        in {"serialization.py", "store.py", "history.py", "json.py"}
        and name
        in {
            "plan_bytes",
            "run_bytes",
            "plan_digest",
            "run_digest",
            "validate_record",
            "records",
            "read_plan",
            "read_run",
            "encode",
        }
    }


def history_operation(
    path: Path, first: str, last: str, name: str
) -> Callable[[], object]:
    from apizr.experiments import comparison
    from apizr.experiments.history import history_bytes, list_runs, show_run

    if name == "list":
        return lambda: history_bytes(list_runs(path))
    if name == "show":
        return lambda: history_bytes(show_run(path, first))
    # Baseline and optimized source use the command's own composition, so both
    # include complete history validation and final JSON serialization.
    compare_stored = getattr(comparison, "compare_stored_runs", None)
    if compare_stored is not None:
        return lambda: comparison.diff_bytes(compare_stored(path, first, last))
    return lambda: comparison.diff_bytes(
        comparison.compare_runs(show_run(path, first), show_run(path, last))
    )


def run(output: Path, *, repeats: int, sizes: list[int]) -> dict[str, Any]:
    from apizr.experiments._files import fingerprint_file
    from apizr.experiments.serialization import read_plan, read_run
    from apizr.experiments.store import MAX_ENTRIES, MAX_READ_BYTES, publish
    from apizr.tracking import session

    project = output / "fixtures"
    project.mkdir()
    notebook = ROOT / "examples/data-science/fraud-detection/fraud_detection.ipynb"
    shutil.copy2(notebook, project / notebook.name)
    script = project / "large.py"
    script.write_text(
        "\n".join(
            f"def feature_{n}(value: float) -> float:\n    return value * {n + 1}\n"
            for n in range(500)
        )
    )
    (project / "apizr.toml").write_text('schema_version="apizr.project/v1"\nroot="."\n')
    (project / "operator.json").write_text(
        json.dumps(
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
                        "store": "history-10",
                        "permissions": ["experiments.read"],
                    },
                ],
            }
        )
    )
    measurements: dict[str, Any] = {}
    report: dict[str, Any] = {
        "schema": "apizr.engine-benchmark/v1",
        "recorded_at": datetime.now(UTC).isoformat(),
        "commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
        ),
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "src/apizr/experiments/store.py",
                "src/apizr/experiments/history.py",
                "src/apizr/experiments/serialization.py",
                "src/apizr/experiments/comparison.py",
                "src/apizr/workspace/editor_session.py",
                "src/apizr/cli/commands/experiment.py",
                "src/apizr/experiments/values.py",
                "src/apizr/tracking/__init__.py",
                "src/apizr/tracking/session.py",
                "src/apizr/tracking/decorator.py",
                "src/apizr/tracking/kernel.py",
                "src/apizr/tracking/adapters.py",
                "src/apizr/tracking/budget.py",
                "scripts/qualification/experiments/benchmark_engine.py",
            )
            if (ROOT / name).is_file()
        },
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "runner": os.environ.get("RUNNER_NAME", "local"),
        "logical_cpus": os.cpu_count(),
        "lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "method": {
            "repeats": repeats,
            "clock": "perf_counter",
            "history_cache": "OS cache may be warm; no application cache across commands",
            "fixture_creation_timed": False,
            "durable_publication": True,
            "host_exclusivity": "Shared local/hosted machine; other workloads are not controlled",
        },
        "limits": {
            "entries_per_directory": MAX_ENTRIES,
            "aggregate_read_bytes": MAX_READ_BYTES,
        },
        "fixtures": {
            path.name: {
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in (notebook, script)
        },
        "measurements": measurements,
    }

    def retain(name: str, operation: Callable[[], object]) -> None:
        print(name, flush=True)
        measurements[name] = measure(operation, repeats)
        (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")

    for name, arguments in (
        ("import_apizr", ["-c", "import apizr"]),
        ("import_tracking", ["-c", "import apizr.tracking"]),
        ("cli_version", ["-m", "apizr.cli", "--version"]),
    ):
        retain(name, lambda arguments=arguments: command(arguments))
    for source in (project / notebook.name, script):
        retain(
            "inspect_" + source.suffix[1:],
            lambda source=source: command(
                [
                    "-m",
                    "apizr.cli",
                    "experiment",
                    "inspect",
                    str(source),
                    "--root",
                    str(project),
                    "--format",
                    "json",
                ]
            ),
        )
    for size in (0, 1024**2, 16 * 1024**2):
        path = project / f"digest-{size}.bin"
        path.write_bytes(b"x" * size)
        retain(
            f"digest_{size}",
            lambda path=path, size=size: fingerprint_file(
                project, path.name, max(1, size)
            ),
        )

    fixture = ROOT / "tests/fixtures/experiments/v1"
    plan = read_plan((fixture / "plan.json").read_bytes())
    run_value = read_run((fixture / "run.json").read_bytes())
    from apizr.experiments.model import ExperimentPlan, ExperimentRun

    assert isinstance(plan, ExperimentPlan) and isinstance(run_value, ExperimentRun)
    publication = 0

    def publication_once() -> None:
        nonlocal publication
        publication += 1
        publish(project / f"publication-{publication}", plan, run_value)

    retain("publication_empty_store", publication_once)
    cold_number = 0

    def cold_once() -> None:
        nonlocal cold_number
        cold_number += 1
        cold_session(ROOT / "src", project / f"cold-session-{cold_number}")

    retain("sdk_cold_empty_session", cold_once)
    session_number = 0
    for count in (0, 256):
        entries, values, exits = [], [], []
        for _ in range(repeats):
            session_number += 1
            start = time.perf_counter()
            capture = session(root=project, store=project / f"session-{session_number}")
            capture.__enter__()
            entered = time.perf_counter()
            for number in range(count):
                capture.log_metric(f"metric_{number}", number)
            logged = time.perf_counter()
            capture.__exit__(None, None, None)
            exited = time.perf_counter()
            entries.append(entered - start)
            values.append((logged - entered) / max(count, 1))
            exits.append(exited - logged)
        for suffix, samples in (
            ("entry", entries),
            ("per_value", values),
            ("exit", exits),
        ):
            measurements[f"sdk_{count}_{suffix}"] = {
                "seconds": samples,
                "median_seconds": statistics.median(samples),
                "outcome": "success",
            }
    for size in sizes:
        path = project / f"history-{size}"
        print(f"Prepare {size} canonical Runs (not timed)", flush=True)
        first, last = make_history(path, size)
        for name in ("list", "show", "diff"):
            operation = history_operation(path, first, last, name)
            retain(f"history_{size}_{name}", operation)
            if size <= MAX_ENTRIES:
                measurements[f"history_{size}_{name}"]["profile_calls"] = profile(
                    operation, output / f"history-{size}-{name}.prof"
                )
        if size == 10:
            for operation, arguments in (
                ("capabilities", {}),
                ("experiment_list", {}),
                ("experiment_show", {"run_id": first}),
                ("experiment_diff", {"run_a": first, "run_b": last}),
            ):
                request = json.dumps(
                    {
                        "schema_version": "apizr.editor/v1",
                        "request_id": "benchmark",
                        "operation": operation,
                        "arguments": arguments,
                    }
                ).encode()

                def editor_roundtrip(request=request) -> None:
                    response = json.loads(
                        command(
                            [
                                "-m",
                                "apizr.cli",
                                "editor",
                                "--project",
                                str(project / "apizr.toml"),
                                "--operator-policy",
                                str(project / "operator.json"),
                                "--store",
                                "history-10",
                            ],
                            stdin=request,
                        )
                    )
                    if not response["ok"]:
                        raise ValueError(
                            "benchmark_editor_refused: "
                            + json.dumps(response["diagnostics"])
                        )

                retain("editor_" + operation, editor_roundtrip)
    report["result"] = "pass"
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3, choices=range(1, 21))
    parser.add_argument(
        "--history-sizes", type=int, nargs="+", default=[10, 1000, 10000]
    )
    args = parser.parse_args()
    if any(size not in {10, 1000, 4096, 10000} for size in args.history_sizes):
        parser.error("Retained history sizes: 10, 1000, 4096, 10000")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    run(output, repeats=args.repeats, sizes=args.history_sizes)


if __name__ == "__main__":
    main()
