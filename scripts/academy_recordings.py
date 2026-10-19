"""Bind Academy pages to the retained recordings and render their actual narration."""

import hashlib
import json
import re
from pathlib import Path


def recordings(root: Path) -> dict:
    data = json.loads((root / "academy/recordings.json").read_text())
    if data.get("schema") != "apizr.academy-recordings/v1":
        raise ValueError("Unknown Academy recording catalogue")
    lessons = data["lessons"]
    if len(lessons) != 12 or {r["number"] for r in lessons} != set(range(1, 13)):
        raise ValueError("Academy must identify each of the twelve recordings once")
    for field in ("id", "page", "video_id"):
        if len({r[field] for r in lessons}) != 12:
            raise ValueError(f"Duplicate Academy recording {field}")
    for record in lessons:
        if not re.fullmatch(r"[\w-]{11}", record["video_id"]):
            raise ValueError("Invalid recorded video identity")
        thumbnail = record["thumbnail"]
        if (
            thumbnail["path"]
            != f"assets/videos/academy-{record['number']:02}-youtube.jpg"
            or not re.fullmatch(
                rf"https://i\.ytimg\.com/vi/{re.escape(record['video_id'])}/(?:maxresdefault|hqdefault)\.jpg",
                thumbnail["source_url"],
            )
        ):
            raise ValueError("Thumbnail does not belong to this published video")
        image = (root / "docs" / thumbnail["path"]).read_bytes()
        if (
            image[:2] != b"\xff\xd8"
            or hashlib.sha256(image).hexdigest() != thumbnail["sha256"]
        ):
            raise ValueError("Published video thumbnail changed")
        if not record["chapters"]:
            raise ValueError("Missing recorded chapters")
        times = [c["seconds"] for c in record["chapters"]]
        if (
            times[0] != 0
            or any(b <= a for a, b in zip(times, times[1:], strict=False))
            or times[-1] >= record["duration_seconds"]
            or any(not c["narration"].strip() for c in record["chapters"])
        ):
            raise ValueError("Invalid recording timeline or narration")
    for name, digest in data["downloads"].items():
        path = Path(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or path.parts[0] != "downloads"
            or hashlib.sha256((root / "docs" / path).read_bytes()).hexdigest() != digest
        ):
            raise ValueError(f"Recorded teaching material changed: {name}")
    return data


def lesson_markdown(markdown: str, page, catalogue: dict) -> str:
    identity = page.meta.get("recording")
    if identity is None:
        if "lesson" in page.meta:
            raise ValueError("Academy course has no recording identity")
        return markdown
    matches = [r for r in catalogue["lessons"] if r["id"] == identity]
    if len(matches) != 1:
        raise ValueError(f"Unknown recording: {identity}")
    record = matches[0]
    if (
        page.meta.get("lesson") != record["number"]
        or page.meta.get("title") != record["title"]
        or re.findall(r"^# (.+)$", markdown, re.MULTILINE) != [record["title"]]
        or page.file.src_uri != record["page"]
        or re.findall(r'data-apizr-video="([^"]+)"', markdown) != [record["video_id"]]
        or re.findall(r'data-apizr-title="([^"]+)"', markdown) != [record["title"]]
        or f'src="../../{record["thumbnail"]["path"]}"' not in markdown
        or markdown.count("<!-- recording-transcript -->") != 1
    ):
        raise ValueError(f"Course, video and recording do not agree: {identity}")
    edition = record["recording_version"] + (
        " development candidate" if record["number"] >= 6 else ""
    )
    lines = [
        f"English · {record['duration']} · Recorded with Apizr **{edition}**.",
        "",
        '??? info "Chapters in this recording"',
        "",
        "    | Time | Chapter |",
        "    | --- | --- |",
    ]
    for chapter in record["chapters"]:
        lines.append(f"    | {chapter['time']} | {chapter['title']} |")
    lines += [
        "",
        '??? quote "Read the recording transcript and commands"',
        "",
        "    This is the retained English narration, in the original chapter order. Commands keep the recorded version and prerequisites; setup additions in the lesson are labelled separately.",
    ]
    for chapter in record["chapters"]:
        lines += ["", f"    **{chapter['time']} — {chapter['title']}**", ""]
        lines += ["    " + line for line in chapter["narration"].splitlines()]
        for command in chapter["commands"]:
            if command["expected_exit"]:
                lines += ["", f"    Expected refusal: exit {command['expected_exit']}."]
            lines += ["", "    ```sh"]
            lines += ["    " + line for line in command["text"].splitlines()]
            lines += ["    ```"]
    return markdown.replace("<!-- recording-transcript -->", "\n".join(lines))
