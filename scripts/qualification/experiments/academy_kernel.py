"""Execute the trusted Academy notebook in a real installed ipykernel.

This is an explicit local recording operation with host access, not a sandbox.
Reuse the qualified kernel lifecycle; never manufacture terminal or cell output.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

from apizr.experiments import CaptureMode
from scripts.qualification.experiments.experiment_jupyter_proof import Kernel, found


def record(notebook: Path, workspace: Path, *, pause: float = 0):
    if not 0 <= pause <= 5:
        raise ValueError("Pause must be between zero and five seconds")
    workspace = workspace.resolve()
    checkout = Path(__file__).resolve().parents[3]
    if workspace.is_relative_to(checkout) or workspace.exists():
        raise ValueError("Use a new workspace outside the checkout")
    source = notebook.read_bytes()
    cells = [c for c in json.loads(source)["cells"] if c["cell_type"] == "code"]
    repeat = next(c for c in cells if c["id"] == "first-variant")
    workspace.mkdir(parents=True)
    kernel = Kernel(workspace)
    observed = []
    try:
        for cell in [*cells, repeat]:
            code = "".join(cell["source"])
            print(f"\nExecute live kernel cell: {cell['id']}\n{code}", flush=True)
            reply, messages = kernel.execute(code, cell["id"])
            for message in messages:
                content = message["content"]
                if message["msg_type"] == "stream":
                    print(content["text"], end="", flush=True)
                elif message["msg_type"] in {"execute_result", "display_data"}:
                    print(content["data"].get("text/plain", ""), flush=True)
            observed.append(
                {"cell_id": cell["id"], "execution_count": reply["execution_count"]}
            )
            print("Kernel execution count:", reply["execution_count"], flush=True)
            time.sleep(pause)
    finally:
        kernel.close()
    retained = found(kernel)
    assert len(retained) == 4
    assert {r.run.capture.mode for r in retained} == {
        CaptureMode.JUPYTER_CELL,
        CaptureMode.DECORATED_CALL,
    }
    assert all(r.run.capture.cell.execution_count is not None for r in retained)
    variants = [r for r in retained if r.run.capture.cell.cell_id == repeat["id"]]
    assert len(variants) == 2
    assert len({r.run.capture.cell.execution_count for r in variants}) == 2
    evidence = {
        "schema": "apizr.academy-live-kernel/v1",
        "result": "passed",
        "notebook_sha256": hashlib.sha256(source).hexdigest(),
        "cells": observed,
        "runs": [r.run_digest for r in retained],
        "capture_modes": sorted({r.run.capture.mode.value for r in retained}),
        "simulated_kernel": False,
    }
    (workspace / "kernel-evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n"
    )
    print(
        f"\nRetained {len(retained)} real live-kernel Runs; repeated cell identity preserved.",
        flush=True,
    )
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--pause", type=float, default=0)
    args = parser.parse_args()
    record(args.notebook, args.workspace, pause=args.pause)


if __name__ == "__main__":
    main()
