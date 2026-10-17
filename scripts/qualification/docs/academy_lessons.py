"""Prepare Academy VI-XII from existing guides for the established video process.

This exports source/shot lists only. It does not introduce a rendering pipeline,
invent published video URLs or change existing Academy recordings.
"""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GUIDES = ROOT / "docs/getting-started/user-guide"
LESSONS = (
    (
        "VI",
        "inspection",
        "Inspect experiment evidence",
        "experiment-inspection.md",
        "experiment-inspection:example",
        "Inspect without executing the script. Read Code, Data, Parameters, Randomness, Environment, Metrics, Outputs and Serving. Explain the unresolved input and distinguish captured evidence from reproducibility.",
    ),
    (
        "VII",
        "history",
        "Run an experiment and read its history",
        "experiment-runs.md",
        "experiment-run:guide",
        "Show the source, explicitly choose trusted execution, then inspect the Plan, Run, metric and output. Explain that this local process has host access and is not a sandbox.",
    ),
    (
        "VIII",
        "comparison",
        "Compare experiment Runs",
        "experiment-comparison.md",
        "experiment-diff:guide",
        "Record both variants, compare intended and observed values, and delete the source before comparing the retained history again. A changed parameter and metric are not a causal claim.",
    ),
    (
        "IX",
        "exposure",
        "Expose a selected prediction",
        "experiment-exposure.md",
        "experiment-exposure:guide",
        "Show the main guard separating training from prediction, select exactly one capability and the recorded model, then generate REST and MCP. Show the retained model and excluded debug artifact. Exposure does not retrain or approve promotion.",
    ),
    (
        "X",
        "sdk",
        "Capture Python calls with sessions and decorators",
        "../tracking.md",
        "tracking-journey:session,tracking-journey:decorator,tracking-journey:history",
        "Record the existing session example and both decorated calls. Show the shared history, explicit observations and the unchanged return values. In-memory data has unknown content identity; telemetry remains off by default.",
    ),
    (
        "XI",
        "jupyter",
        "Capture real Jupyter cells",
        "../tracking.md",
        None,
        "Use the committed live-capture notebook in the qualified ipykernel. Run the block and both decorated calls, repeat a cell, and show cell identity/execution count and shared CLI history. Do not substitute experiment run, which exports ordinary Python rather than using a live kernel.",
    ),
    (
        "XII",
        "vscode",
        "Inspect and compare Runs in VS Code",
        "../../reference/vscode.md",
        None,
        "Use the real qualified installed VSIX and explicit engine. Inspect saved Python and notebook source, open a location, refresh the same history, show a Run and compare two. Demonstrate stale results after an edit and the Restricted Mode refusal without starting an engine.",
    ),
)


# Scene inputs for the existing Parts I–V narrator, recorder and editor.
# A prepared scene is not a claim that a recording has passed review.
STORIES = {
    "VI": {
        "hero": ["Read evidence.", "Find what", "is unknown."],
        "intro": "Welcome back to Apizr Academy. In this lesson we inspect an experiment before running it. We use the zero point four point six candidate and a small example from the written guide. Inspection reads source evidence. It does not execute the training code.",
        "items": [
            ["Inspect", "Read the source without running it"],
            ["Locate", "Separate known evidence from unresolved inputs"],
            ["Continue", "Use the written guide for the current release"],
        ],
        "map": "The report separates code, data, parameters, randomness, environment, metrics, outputs and serving. Those sections describe evidence that Apizr can identify. They are not a guarantee that this experiment is reproducible. An unresolved input stays visible instead of becoming a guessed value.",
        "demo": "These are the exact commands from the inspection guide. The source reads a local training file and refers to a validation path that has not been defined. It also names a learning rate, a metric and a prediction function. We run inspect in its readable and JSON forms. The script itself is not run, so the unresolved names do not turn into a training failure. Read the data evidence and the unknown validation input. Finding a prediction function also does not approve exposing it as a service.",
        "detail": "apizr experiment inspect example.py | sed -n '49,78p'",
        "commands": [
            [1, "apizr --version"],
            [4, "cat guide-commands.sh"],
            [14, "bash guide-commands.sh > guide-output.log"],
            [16, "apizr experiment inspect example.py | sed -n '1,24p'"],
            [30, "apizr experiment inspect example.py | sed -n '25,48p'"],
            [43, "apizr experiment inspect example.py | sed -n '49,78p'"],
        ],
        "takeaway": "Static evidence includes unknowns; inspection does not run training.",
        "recap": "Inspection gives us a starting point for review. We have not trained a model or proved reproducibility. In the next lesson we make the separate decision to run a trusted local script and retain its observations. Follow the linked written guide when commands change.",
    },
    "VII": {
        "hero": ["Run locally.", "Retain", "the evidence."],
        "intro": "Welcome back to Apizr Academy. This lesson moves from source inspection to an actual local experiment Run. We use a tiny trusted Python script, record a metric and an output, then read the shared history. Running code is an explicit decision with access to the host.",
        "items": [
            ["Plan", "Inspect before choosing execution"],
            ["Run", "Execute a trusted local script"],
            ["History", "Read retained metrics and outputs"],
        ],
        "map": "A Plan describes the intended execution. A Run retains what was observed. The local process is not a sandbox. Only run code you trust, in an environment you have chosen. Recording a metric or an output does not establish that a result should be promoted.",
        "demo": "The guide writes a short script that calculates a mean and saves a model file. First we inspect it. The run command then executes this trusted script and explicitly selects the mean metric and model output. Its JSON result supplies the Run digest. List reads the local history, and show opens the selected Run. Notice the difference between the source Plan and the recorded observation. Finally we read the model file itself. These are real local commands against the installed candidate, not prewritten terminal output.",
        "detail": "cat model.json && apizr experiment list",
        "takeaway": "Execution is explicit; a Run retains selected observations.",
        "recap": "We now have a retained Run, a metric and an output. History gives us an identity we can inspect later. It does not certify the scientific method or isolate the executed process. The next lesson records a second variant and compares the evidence.",
    },
    "VIII": {
        "hero": ["Compare Runs.", "Read changes.", "Keep context."],
        "intro": "Welcome back to Apizr Academy. We now compare two experiment Runs. Our small example changes a parameter and a recorded score. We then remove the original script and compare the retained history again. A comparison describes changes without claiming that one caused another.",
        "items": [
            ["Record", "Retain two explicit variants"],
            ["Compare", "Read intended and observed differences"],
            ["Retain", "Compare after the source has been removed"],
        ],
        "map": "Each run has its own retained identity. The diff uses that history, rather than rereading whichever script happens to be present now. A changed parameter and a changed metric can appear together. That alone is not evidence of causation or a model approval.",
        "demo": "We use the exact comparison guide. The first variant sets the maximum depth to eight and the score to zero point nine one. The second uses twelve and zero point nine two. Both Runs explicitly record the score as the metric. We list the retained Runs and compare their digests. The guide then deletes the source script and writes another comparison in JSON. The final commands confirm that the source is gone and the comparison still exists. Retained evidence makes this review possible without silently substituting the latest source file.",
        "detail": 'test ! -e compare_train.py && python3 -c \'import json; d=json.load(open("comparison.json")); p=d["parameters"][0]; m=d["metrics"][0]; print("max_depth:",p["observed_a"]["value"],"->",p["observed_b"]["value"]); print("roc_auc:",m["a"]["value"],"->",m["b"]["value"]); print("Retained comparison available after source deletion")\'',
        "takeaway": "Compare retained evidence; a changed score is not a causal claim.",
        "recap": "We compared two retained Runs before and after removing the source. This establishes what the history contains, not why the score changed. Keep the execution context and scientific review alongside any comparison. Next we select one recorded prediction for exposure.",
    },
    "IX": {
        "hero": ["Select once.", "Bind serving.", "Keep scope."],
        "intro": "Welcome back to Apizr Academy. This lesson selects a recorded prediction and generates REST and MCP bindings. Training writes a model and a debug artifact. We expose only the prediction capability and the model artifact. Generating these bindings does not retrain or approve a deployment.",
        "items": [
            ["Separate", "Keep training behind the main guard"],
            ["Select", "Choose one capability and its model"],
            ["Generate", "Create local REST and MCP bindings"],
        ],
        "map": "The main guard keeps training separate from prediction when the module is imported. The operator policy grants source analysis for this exact local directory. The expose command selects a capability, an interface and a recorded artifact. These choices define the serving scope.",
        "demo": "These commands come directly from the exposure guide. Running the trusted script writes a model and a debug file, and both are recorded as outputs. We then choose the prediction capability and select only the model for each interface. The generated REST and MCP directories are local artifacts. We inspect the binding descriptions and their retained files. The debug output was recorded for the experiment but was not selected for serving. This lesson stops at generation: it does not start a service, publish an image or promote the model.",
        "detail": 'python3 -c \'import json; files=["rest-binding.json","mcp-binding.json"]; [(lambda b: print(b["interface"], b["capability"], [(o["name"],o["reference"]) for o in b["outputs"]]))(json.load(open(f))["binding"]) for f in files]\'',
        "takeaway": "One selected prediction and model; generation does not promote a model.",
        "recap": "We have explicit local REST and MCP bindings for the selected prediction. Training, experiment evidence and serving selection remain separate decisions. Review the written guide for the current contract before moving to service qualification or deployment.",
    },
    "X": {
        "hero": ["Keep Python.", "Capture calls.", "Read history."],
        "intro": "Welcome back to Apizr Academy. We now capture ordinary Python calls with the SDK. We use a session for a block and a decorator for a function. Both write into the same local experiment history without replacing the original return values.",
        "items": [
            ["Session", "Capture a block with explicit observations"],
            ["Decorator", "Capture each call and keep its return value"],
            ["History", "Read the same local Runs from the CLI"],
        ],
        "map": "Inputs, parameters and metrics are explicit observations. An in-memory input has unknown content identity unless you supply evidence for it. The SDK does not turn unknown data into a verified snapshot. Telemetry remains off by default, and this candidate has no production sender.",
        "demo": "The first guide example opens a tracking session. It records an input name, a threshold and a mean, then prints the retained Run digest. The second example decorates an evaluation function and calls it with two thresholds. Each call keeps its normal result and creates its own Run. Finally the command line lists the same history. We have not needed a training framework for this small example. When you use scientific libraries, those dependencies still belong to your own environment. The next lesson uses the same API inside a real live notebook kernel.",
        "detail": "apizr experiment list",
        "takeaway": "Explicit SDK observations share CLI history and preserve return values.",
        "recap": "Sessions capture blocks, and decorators capture calls. Both preserve explicit evidence in the shared local history. Unknown input identity stays unknown. Continue with the live-kernel notebook and VS Code guides for those interfaces; these require their own actual interface recordings.",
    },
}


STORIES["XI"] = {
    "hero": ["Keep cells.", "Capture calls.", "Share history."],
    "intro": "Welcome back to Apizr Academy. We now use the same tracking API inside a real live "
    "Jupyter kernel. A small recording driver sends the committed notebook cells to an "
    "installed ipykernel. This terminal view shows actual cell execution and output, "
    "rather than a notebook interface or an exported Python script.",
    "items": [
        ["Kernel", "Run the committed notebook in a live ipykernel"],
        ["Repeat", "Keep cell identity and a new execution count"],
        ["History", "Read the same retained Runs from the CLI"],
    ],
    "map": "The session captures a block, and the decorator captures each function call. In a "
    "live kernel their evidence includes the executing cell identity and count. Repeating "
    "a cell produces another Run. In-memory input identity and the saved notebook identity "
    "remain unknown unless explicitly supplied.",
    "demo": "The recording driver opens a real kernel using the candidate interpreter. It sends "
    "each committed code cell with its own cell identifier and prints the actual kernel "
    "messages. The session reports its execution count. Two calls then return their "
    "normal scores. We repeat the first variant cell, keeping its identifier while the "
    "execution count advances. The retained history contains four Runs: one session and "
    "three decorated calls. The final command reads that same store through the command "
    "line. No experiment run export is used, and the SDK has not started a kernel behind "
    "the user’s back.",
    "detail": "apizr experiment list --store "
    '"$APIZR_ACADEMY_KERNEL_WORKSPACE/.apizr/experiments/v1"',
    "commands": [
        [1, "apizr --version"],
        [4, "ls -l jupyter-capture.ipynb"],
        [
            8,
            "python -m scripts.qualification.experiments.academy_kernel --notebook "
            'jupyter-capture.ipynb --workspace "$APIZR_ACADEMY_KERNEL_WORKSPACE" --pause 3',
        ],
        [
            43,
            "apizr experiment list --store "
            '"$APIZR_ACADEMY_KERNEL_WORKSPACE/.apizr/experiments/v1"',
        ],
    ],
    "takeaway": "Real kernel cells retain identity and execution count; history is shared.",
    "recap": "We have captured real live-kernel cells, including a repeated cell. The decorator "
    "still records decorated calls, and both capture styles preserve cell evidence. This "
    "does not identify unsaved notebook content as a saved file or establish a serving "
    "binding. Use the written notebook guide for the current contract.",
}


def episode_files(directory, part, title, commands):
    """Write compatible inputs; rendering still uses the original local tools."""
    if part not in STORIES:
        return
    story = STORIES[part]
    number = f"{[p[0] for p in LESSONS].index(part) + 6:02}"
    production = directory / "production"
    production.mkdir()
    if commands:
        (production / "guide-commands.sh").write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n\n" + commands + "\n"
        )
    episode = {
        "number": number,
        "title": title,
        "repository": "Alien6-Studio/outerspace-apizr",
        "ref": "0.4.6 candidate",
        "version": "0.4.6",
        "hero": story["hero"],
    }
    scenes = [
        {
            "id": "intro",
            "title": title,
            "voice": story["intro"],
            "kind": "hero",
            "seconds": 0,
            "items": [],
        },
        {
            "id": "map",
            "title": "Three decisions",
            "voice": story["map"],
            "kind": "recap",
            "seconds": 0,
            "items": story["items"],
        },
        {
            "id": "demonstration",
            "title": title,
            "voice": story["demo"],
            "seconds": 64,
            "capture": "demonstration.mp4",
            "commands": story.get(
                "commands",
                [
                    [1, "apizr --version"],
                    [4, "cat guide-commands.sh"],
                    [14, "bash guide-commands.sh"],
                    [43, story["detail"]],
                ],
            ),
            "takeaway": story["takeaway"],
        },
        {
            "id": "recap",
            "title": "What this evidence establishes",
            "voice": story["recap"],
            "kind": "recap",
            "seconds": 0,
            "items": story["items"],
        },
        {
            "id": "end",
            "title": "Continue with the written guide",
            "voice": "The current written guide remains authoritative. Continue there for the detailed steps. Thank you for following Apizr Academy.",
            "kind": "end",
            "seconds": 0,
            "items": [["Apizr", "Alien6-Studio/outerspace-apizr"]],
        },
    ]
    for scene in scenes:
        scene.setdefault("section", title.upper())
        scene.setdefault("repository", episode["repository"])
        scene.setdefault("ref", episode["ref"])
        scene.setdefault("takeaway", "")
    (production / "episode.json").write_text(json.dumps(episode, indent=2) + "\n")
    (production / "narration.json").write_text(json.dumps(scenes, indent=2) + "\n")


def block(text, marker):
    matches = re.findall(
        r"<!-- " + re.escape(marker) + r" -->\s*```sh\n(.*?)\n```", text, re.S
    )
    if len(matches) != 1:
        raise ValueError("Missing or ambiguous executable guide block: " + marker)
    return matches[0]


def prepare(output, *, root=ROOT):
    output = output.resolve()
    if output.is_relative_to(root.resolve()) or output.exists():
        raise ValueError("Use a new output directory outside the repository")
    inputs = []
    # Validate every marker before writing any visible output.
    for part, slug, title, page, markers, shots in LESSONS:
        path = root / "docs/getting-started/user-guide" / page
        text = path.read_text()
        commands = (
            "\n\n".join(block(text, m) for m in markers.split(",")) if markers else None
        )
        inputs.append((part, slug, title, path.resolve(), commands, shots))
    package = json.loads((root / "editors/vscode/package.json").read_text())
    output.mkdir(parents=True)
    records = []
    for part, slug, title, path, commands, shots in inputs:
        directory = output / (part.lower() + "-" + slug)
        directory.mkdir()
        (directory / "shot-list.md").write_text(
            f"# Academy Part {part} — {title}\n\n"
            "Status: preparation; no recording or publication is established.\n\n"
            "Continue the existing Parts I–V production process: English narration "
            "and captions, actual product operations, existing visual identity and "
            "privacy-enhanced click-to-load embedding after approval.\n\n"
            + shots
            + "\n\nUse the existing opener, voice, captions, editor layout, "
            "closing sequence and cover template from the original video project. "
            "Final duration and public URL are recorded only after the actual approved export.\n"
        )
        if commands:
            (directory / "guide-commands.sh").write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\n\n" + commands + "\n"
            )
        if part in STORIES:
            episode_files(directory, part, title, commands)
        if part == "XI":
            notebook = root / "examples/tracking/jupyter-capture.ipynb"
            (directory / notebook.name).write_bytes(notebook.read_bytes())
        if part == "XII":
            command_ids = {
                "apizr.selectEngine",
                "apizr.checkEngine",
                "apizr.inspect",
                "apizr.refreshRuns",
                "apizr.showRun",
                "apizr.compareRuns",
            }
            commands_ui = [
                c
                for c in package["contributes"]["commands"]
                if c["command"] in command_ids
            ]
            if {c["command"] for c in commands_ui} != command_ids:
                raise ValueError("VS Code shot list references unavailable commands")
            (directory / "product-commands.json").write_text(
                json.dumps(commands_ui, indent=2) + "\n"
            )
        records.append(
            {
                "part": part,
                "title": title,
                "directory": directory.name,
                "guide": path.relative_to(root.resolve()).as_posix(),
                "guide_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "status": "prepared",
                "video_url": None,
                "duration_seconds": None,
                "files": [
                    {
                        "name": p.relative_to(directory).as_posix(),
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    }
                    for p in sorted(directory.rglob("*"))
                    if p.is_file()
                ],
            }
        )
    manifest = {
        "schema": "apizr.academy-preparation/v1",
        "target_version": package["version"],
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "source_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=root, text=True
            ).strip()
        ),
        "recording_pipeline": "reuse original Parts I–V production project",
        "lessons": records,
        "publication_performed": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.output)
    print(
        json.dumps(
            {
                "result": "prepared",
                "lessons": len(result["lessons"]),
                "publication_performed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
