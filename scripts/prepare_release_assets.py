"""Stage reviewed release attachments without building, uploading or tagging.

Public names come from recorded targets. Target archives are copied byte-for-byte.
On master, GitHub provenance is verified before any output is made visible.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from coordinated_distributions import PROJECTS, digest, record, verify_records, write

REPOSITORY = "Alien6-Studio/outerspace-apizr"


def stream_digest(stream):
    value = hashlib.sha256()
    while block := stream.read(1024 * 1024):
        value.update(block)
    return value.hexdigest()


def member_bytes(archive, name):
    members = [m for m in archive.getmembers() if m.name.removeprefix("./") == name]
    if (
        len(members) != 1
        or not members[0].isfile()
        or members[0].size > 8 * 1024 * 1024
    ):
        raise ValueError("Missing or invalid evidence member: " + name)
    stream = archive.extractfile(members[0])
    assert stream is not None
    return stream.read()


def bound_file(archive, name, path):
    members = [m for m in archive.getmembers() if m.name.removeprefix("./") == name]
    if len(members) != 1 or not members[0].isfile():
        raise ValueError("Missing signed evidence member: " + name)
    stream = archive.extractfile(members[0])
    assert stream is not None
    if members[0].size != path.stat().st_size or stream_digest(stream) != digest(path):
        raise ValueError("Artifact differs from signed evidence: " + name)


def inspect_target(path, candidate):
    with tarfile.open(path) as archive:
        target = json.loads(member_bytes(archive, "target.json"))
        if (
            target["schema"] != "apizr.release-target/v1"
            or target["commit"] != candidate["commit"]
        ):
            raise ValueError("Target source mismatch")
        expected = {i["file"]: i for i in target["artifacts"]}
        if len(expected) != len(target["artifacts"]):
            raise ValueError("Duplicate target inventory")
        seen = set()
        for member in archive.getmembers():
            name = member.name.removeprefix("./")
            if (
                Path(name).is_absolute()
                or ".." in Path(name).parts
                or member.issym()
                or member.islnk()
            ):
                raise ValueError("Unsafe target member")
            if member.isdir():
                continue
            if not member.isfile() or name in seen:
                raise ValueError("Invalid or duplicate target member")
            seen.add(name)
            if name == "target.json":
                continue
            item = expected.get(name)
            if item is None or member.size != item["bytes"]:
                raise ValueError("Unrecorded target member")
            stream = archive.extractfile(member)
            assert stream is not None
            if stream_digest(stream) != item["sha256"]:
                raise ValueError("Changed target member")
        if seen != set(expected) | {"target.json"}:
            raise ValueError("Missing target members")
    info = target["target"]
    system = {"Linux": "linux", "Darwin": "macos"}[info["system"]]
    machine = info["machine"]
    python = info["python"]
    if not re.fullmatch(r"[A-Za-z0-9_]+", machine) or not re.fullmatch(
        r"3\.(11|12|13|14)\.\d+", python
    ):
        raise ValueError("Unsupported recorded target")
    return target, f"{system}-{machine}-cpython-{python}"


def prepare(downloads: Path, output: Path, commit: str, run_id: int, preview=False):
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or run_id <= 0 or output.exists():
        raise ValueError("Expected exact source, run and absent output directory")
    candidate_dir = downloads / "release-candidate"
    candidate = json.loads((candidate_dir / "candidate.json").read_text())
    version = candidate["version"]
    if (
        candidate["schema"] != "apizr.release-candidate/v1"
        or candidate["commit"] != commit
        or not re.fullmatch(r"\d+\.\d+\.\d+(?:rc[1-9]\d*)?", version)
    ):
        raise ValueError("Candidate source/version mismatch")
    expected = {
        "dist/" + name.replace("-", "_") + "-" + version + suffix
        for name in PROJECTS
        for suffix in ("-py3-none-any.whl", ".tar.gz")
    }
    if {i["file"] for i in candidate["artifacts"]} != expected or len(
        candidate["artifacts"]
    ) != 8:
        raise ValueError("Expected eight candidate distributions")
    verify_records(candidate_dir, candidate["artifacts"])
    evidence = downloads / "build-attestations"
    signed = evidence / "ci-evidence.tar.gz"
    if not preview:
        subprocess.run(
            [
                "gh",
                "attestation",
                "verify",
                str(signed),
                "--bundle",
                str(evidence / "build-provenance.sigstore.json"),
                "--repo",
                REPOSITORY,
                "--signer-workflow",
                REPOSITORY + "/.github/workflows/ci.yml",
                "--source-digest",
                commit,
                "--source-ref",
                "refs/heads/master",
            ],
            check=True,
            timeout=120,
        )
    targets = sorted(downloads.glob("release-target-*"))
    if len(targets) != 6:
        raise ValueError("Expected six qualified dependency targets")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=output.parent, prefix=".release-assets-"
    ) as temporary:
        staging = Path(temporary) / "assets"
        staging.mkdir()
        entries = []

        def copy(source, name, role, provenance):
            destination = staging / name
            if destination.exists() or source.is_symlink() or not source.is_file():
                raise ValueError("Duplicate or invalid attachment")
            shutil.copyfile(source, destination)
            entries.append(
                {
                    **record(destination, staging),
                    "role": role,
                    "evidence_member": provenance,
                }
            )

        with tarfile.open(signed) if not preview else tempfile.TemporaryFile() as proof:
            if not preview:
                bound_file(
                    proof,
                    "coordinated/release-candidate/candidate.json",
                    candidate_dir / "candidate.json",
                )
            for item in candidate["artifacts"]:
                source = candidate_dir / item["file"]
                if not preview:
                    bound_file(
                        proof, "coordinated/release-candidate/" + item["file"], source
                    )
                copy(
                    source,
                    source.name,
                    "PyPI distribution",
                    "coordinated/release-candidate/" + item["file"],
                )
            copy(
                candidate_dir / "candidate.json",
                "candidate.json",
                "source and package inventory",
                "coordinated/release-candidate/candidate.json",
            )
            verify_records(candidate_dir, candidate["artifacts"])
            for directory in targets:
                source = directory / "target-export.tar.gz"
                target, suffix = inspect_target(source, candidate)
                if target["candidate_sha256"] != digest(
                    candidate_dir / "candidate.json"
                ):
                    raise ValueError("Target candidate identity mismatch")
                report = directory / "qualification/qualification.json"
                qualification = json.loads(report.read_text())
                if (
                    qualification["candidate_sha256"] != target["candidate_sha256"]
                    or qualification["commit"] != commit
                    or qualification["target"] != target["target"]
                ):
                    raise ValueError("Qualification identity mismatch")
                if not qualification.get("core_unchanged") or any(
                    qualification.get(name) != "passed"
                    for name in (
                        "pip",
                        "uv_tool",
                        "pipx",
                        "catalog_resolve_lock_sync",
                        "migration",
                        "extras_local_https_ssh",
                    )
                ):
                    raise ValueError("Incomplete installation qualification")
                if not preview:
                    bound_file(
                        proof,
                        "coordinated/" + directory.name + "/target-export.tar.gz",
                        source,
                    )
                    bound_file(
                        proof,
                        "coordinated/"
                        + directory.name
                        + "/qualification/qualification.json",
                        report,
                    )
                for file, ending, role in [
                    (source, "tar.gz", "catalog and locked dependencies"),
                    (report, "qualification.json", "installation qualification"),
                ]:
                    copy(
                        file,
                        f"apizr-{version}-{suffix}.{ending}",
                        role,
                        "coordinated/"
                        + directory.name
                        + "/"
                        + file.relative_to(directory).as_posix(),
                    )
            delivery = downloads / "release-delivery/outcome.json"
            if json.loads(delivery.read_text())["exit_code"] != 0:
                raise ValueError("Delivery proof did not pass")
            if not preview:
                bound_file(proof, "coordinated/release-delivery/outcome.json", delivery)
        if not preview:
            for name in (
                "ci-evidence.tar.gz",
                "build-provenance.sigstore.json",
                "runtime-sbom.sigstore.json",
            ):
                copy(
                    evidence / name,
                    name,
                    "provenance and complete validation evidence",
                    None,
                )
        write(
            staging / "release-assets.json",
            {
                "schema": "apizr.release-assets/v1",
                "version": version,
                "commit": commit,
                "run_id": run_id,
                "status": "PR preview; no master provenance"
                if preview
                else "provenance verified; human publication approval still required",
                "artifacts": entries,
                "official_images": {
                    "status": "deferred to subsequent deliveries",
                    "published": False,
                },
            },
        )
        (staging / "SHA256SUMS").write_text(
            "".join(f"{digest(p)}  {p.name}\n" for p in sorted(staging.iterdir()))
        )
        staging.rename(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downloads", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument(
        "--preview",
        action="store_true",
        help="PR checks only; never publication approval",
    )
    args = parser.parse_args()
    prepare(args.downloads, args.output, args.commit, args.run_id, args.preview)


if __name__ == "__main__":
    main()
