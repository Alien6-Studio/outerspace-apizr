"""Prepare Academy VI-XII from existing guides for the established video process.

This exports source/shot lists only. It does not introduce a rendering pipeline,
invent published video URLs or change existing Academy recordings.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ROOT / "docs/getting-started/user-guide"
LESSONS = (
    (
        "VI",
        "inspection",
        "Inspect experiment evidence",
        "../data-science.md",
        "science:inspect",
        "Inspect the committed synthetic fraud notebook. Explain each evidence origin, replace the active CSV without execution, read the changed fingerprint and correct an unsupported metric/reproducibility claim.",
    ),
    (
        "VII",
        "history",
        "Run an experiment and read its history",
        "../data-science.md",
        "science:run-a,science:list,science:show",
        "Execute the reviewed fraud notebook. Connect intended Plan, runtime observations and model identity. Replace the active CSV, read retained A and explain why evidence does not restore overwritten artifact bytes.",
    ),
    (
        "VIII",
        "comparison",
        "Compare experiment Runs",
        "../data-science.md",
        "science:run-a,science:run-b,science:diff",
        "Measure both synthetic fraud cohorts with unchanged source/settings. Separate material and result evidence, discuss the changed label-rule limitation, predict inverse deltas and check the actual reverse comparison.",
    ),
    (
        "IX",
        "exposure",
        "Expose a selected prediction",
        "../data-science.md",
        "science:run-b,science:authority,science:rest-expose,science:mcp-expose",
        "Explain the real fraud prediction's feature/helper/model dependencies. Select exact Run, capability, model and scientific wheels. Read both actual bindings and solve a stale-model identity exercise; deployment stays separate.",
    ),
    (
        "X",
        "sdk",
        "Capture Python calls with sessions and decorators",
        "../tracking.md",
        "tracking-journey:session,tracking-journey:decorator,tracking-journey:history",
        "Use the real fraud holdout to evaluate precision, recall and flagged volume at different thresholds. Explain session versus decorator, explicit input identity, unchanged return values and the missing evidence for in-memory-only inputs.",
    ),
    (
        "XI",
        "jupyter",
        "Capture real Jupyter cells",
        "../tracking.md",
        None,
        "Use the committed fraud-threshold notebook in a real ipykernel with explicitly selected evaluation.csv. Predict four captures, repeat a cell, read actual identities/counts and explain live-state versus saved-file limits.",
    ),
    (
        "XII",
        "vscode",
        "Review real experiment Runs in VS Code",
        "../../academy/vscode.md",
        None,
        "Use the installed VSIX and an explicitly selected engine with a fresh Wine example. Review real SDK/Jupyter Runs, inspect saved source, demonstrate stale evidence, compare measured scores and show the Restricted Mode refusal. Keep the draft local until publication is authorized.",
    ),
)


# Narration inputs for the shared Academy renderer.
CURRICULUM = json.loads(Path(__file__).with_name("academy_curriculum.json").read_text())
STORIES = CURRICULUM["lessons"]


def episode_files(directory, part, title, commands):
    """Write compatible inputs; rendering still uses the original local tools."""
    if part not in STORIES:
        return
    story = {
        "intro": "",
        "map": "",
        "demo": "",
        "detail": "",
        "takeaway": "",
        "recap": "",
        "items": [],
        **STORIES[part],
    }
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
    if "scenes" in story:
        scenes = json.loads(json.dumps(story["scenes"])) + [
            story.get("end", scenes[-1])
        ]
        if "subtitle" in story:
            episode["subtitle"] = story["subtitle"]
        episode["curriculum"] = "apizr.academy-curriculum/v2"
        episode["learning_objective"] = story["objective"]
        episode["audience"] = CURRICULUM["audience"]
    if part == "XII":
        episode["recording_interface"] = "vscode-native-window"
    for scene in scenes:
        scene.setdefault("section", title.upper())
        scene.setdefault("repository", episode["repository"])
        scene.setdefault("ref", episode["ref"])
        scene.setdefault("takeaway", "")
    (production / "episode.json").write_text(json.dumps(episode, indent=2) + "\n")
    (production / "narration.json").write_text(json.dumps(scenes, indent=2) + "\n")
    if "scenes" in story:
        notes = [
            f"# Academy {part} — {title}",
            "",
            "Audience: " + CURRICULUM["audience"],
            "",
            "Learning objective: " + story["objective"],
            "",
            "Preparation transcript; actual recorded results remain in the local review evidence.",
        ]
        for scene in scenes:
            notes.extend(["", "## " + scene["title"], "", scene["voice"]])
            for command in scene.get("commands", []):
                if len(command) > 2 and command[2] != 0:
                    notes.extend(["", f"Expected refusal: exit {command[2]}."])
                notes.extend(["", "```sh", command[1], "```"])
        (directory / "lesson-notes.md").write_text("\n".join(notes) + "\n")


def block(text, marker):
    matches = re.findall(
        r"<!-- " + re.escape(marker) + r" -->\s*```sh\n(.*?)\n```", text, re.S
    )
    if len(matches) != 1:
        raise ValueError("Missing or ambiguous executable guide block: " + marker)
    return matches[0]


def extract_materials(root, name, destination):
    manifest = json.loads((root / "downloads.json").read_text())
    archive = root / "docs/downloads" / (name + ".zip")
    if (
        hashlib.sha256(archive.read_bytes()).hexdigest()
        != manifest["sha256"][archive.name]
    ):
        raise ValueError("Academy download bytes differ from their product provenance")
    with zipfile.ZipFile(archive) as data:
        for member in data.infolist():
            path = Path(member.filename)
            if path.parts[0] != name or ".." in path.parts or path.is_absolute():
                raise ValueError("Unsafe Academy archive member")
            if not member.is_dir():
                target = destination.joinpath(*path.parts[1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data.read(member))


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
    package = json.loads((root / "academy/vscode-commands.json").read_text())
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
        if part == "XII":
            extract_materials(root, "wine-vscode", directory / "materials")
            (directory / "learning-objective.md").write_text(
                f"# Part {part} learning objective\n\n"
                + STORIES[part]["objective"]
                + "\n\n"
                + STORIES[part]["prerequisites"]
                + "\n"
            )
        elif part in CURRICULUM["lessons"]:
            materials = directory / "materials"
            extract_materials(root, "fraud-detection", materials)
            shutil.copy2(
                materials / "data/transactions-a.csv",
                materials / "data/transactions.csv",
            )
            shutil.copy2(
                Path(__file__).with_name("academy_lab.py"), materials / "lab.py"
            )
            shutil.copy2(
                Path(__file__).with_name("academy_thresholds.py"),
                materials / "thresholds.py",
            )
            (directory / "learning-objective.md").write_text(
                f"# Part {part} learning objective\n\n"
                + STORIES[part]["objective"]
                + "\n\n"
                + STORIES[part]["prerequisites"]
                + "\n\n"
                + "Materials are copied from the committed synthetic fraud example. Product commands execute real operations; lab.py only projects actual reports except the explicitly selected prepare-holdout action. SDK/Jupyter preparation first executes the trusted notebook and derives evaluation.csv from its actual held-out sample. No scores are hard-coded.\n"
            )
            if part == "XI":
                shutil.copy2(
                    root / "academy/materials/fraud-thresholds.ipynb",
                    materials / "fraud-thresholds.ipynb",
                )
        if part == "XI":
            notebook = root / "academy/materials/jupyter-capture.ipynb"
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
        "product_source_commit": package["product_source_commit"],
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "source_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=root, text=True
            ).strip()
        ),
        "curriculum_sha256": hashlib.sha256(
            Path(__file__).with_name("academy_curriculum.json").read_bytes()
        ).hexdigest(),
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
