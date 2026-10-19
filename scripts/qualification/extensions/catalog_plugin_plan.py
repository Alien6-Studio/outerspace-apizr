"""Generate a development catalog from prepared wheels; export/check, never install.

Run with the installed minimal core, outside the checkout. Preparation/building
and explicit sync/activation belong to the existing proof drivers.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from apizr.cli.commands.plugins import main
from apizr.plugins.catalog import (
    generate_entries,
    load_catalog,
    resolve_profile,
    serialize,
)
from apizr.plugins.catalog.models import (
    Catalog,
    Identity,
    Prerequisite,
    Profile,
    Provenance,
)
from apizr.plugins.lock import check_lock, create_lock

DESCRIPTIONS = {
    "outerspace-apizr-mcp": "Read-only repository analysis over a persistent MCP stdio server.",
    "outerspace-apizr-oci": "Build REST/MCP service images and publish verified OCI images.",
    "outerspace-apizr-attest": "Attest verified deliveries and publish or verify OCI receipts.",
}
PREREQUISITES = {
    "outerspace-apizr-mcp": (),
    "outerspace-apizr-oci": (
        Prerequisite(tool="Docker and Buildx", operations=("build", "push")),
    ),
    "outerspace-apizr-attest": (
        Prerequisite(tool="Docker", operations=("attest",)),
        Prerequisite(
            tool="Continuum Attest",
            operations=("attest", "verify", "publish", "fetch"),
        ),
        Prerequisite(tool="ORAS", operations=("publish", "discover", "fetch")),
    ),
}


def prepare(
    house: Path, locks: dict[str, Path], commit: str, output: Path, profile: str
):
    output.mkdir()
    requirements = house / "requirements"
    requirements.mkdir(exist_ok=True)
    project = output / "declarations.toml"
    lines = ['schema_version = "apizr.project/v1"']
    identities = {}
    for name, lock in sorted(locks.items()):
        wheel = next(house.glob(name.replace("-", "_") + "-*.whl"))
        raw = lock.read_bytes()
        (requirements / (name + ".lock")).write_bytes(raw)
        version = wheel.name.split("-")[1]
        identities[name] = Identity(name=name, version=version)
        lines.extend(
            (
                "[[plugins]]",
                f'name = "{name}"',
                f'version = "{version}"',
                f'sha256 = "{hashlib.sha256(wheel.read_bytes()).hexdigest()}"',
                f'requirements = "requirements/{name}.lock"',
            )
        )
    shutil.copytree(requirements, output / "requirements")
    project.write_text("\n".join(lines) + "\n")
    check = create_lock(project, house, output / "inspected.lock.json")
    (output / "artifact-check.json").write_text(check.model_dump_json())
    if not check.valid:
        raise RuntimeError(check.model_dump_json())
    entries = generate_entries(
        project,
        house,
        descriptions=DESCRIPTIONS,
        provenance=Provenance(
            repository="https://github.com/Alien6-Studio/outerspace-apizr",
            commit=commit,
            status="development",
        ),
        prerequisites=PREREQUISITES,
    )
    profiles = []
    for label, names in (
        ("mcp", ("outerspace-apizr-mcp",)),
        ("oci", ("outerspace-apizr-oci",)),
        ("delivery", ("outerspace-apizr-oci", "outerspace-apizr-attest")),
    ):
        if all(name in identities for name in names):
            profiles.append(
                Profile(name=label, plugins=tuple(identities[name] for name in names))
            )
    catalog = Catalog(entries=entries, profiles=tuple(profiles))
    path = output / "catalogue.json"
    path.write_bytes(serialize(catalog))
    assert main(["catalog", "list", "--catalog", str(path), "--json"]) == 0
    for entry in entries:
        assert (
            main(
                [
                    "catalog",
                    "show",
                    entry.wheel.name,
                    "--version",
                    entry.wheel.version,
                    "--catalog",
                    str(path),
                    "--json",
                ]
            )
            == 0
        )
    assert (
        main(
            [
                "catalog",
                "resolve",
                "--profile",
                profile,
                "--catalog",
                str(path),
                "--wheelhouse",
                str(house),
                "--output-dir",
                str(output / "plan"),
                "--json",
            ]
        )
        == 0
    )
    for selected in profiles:
        plan = output / ("repeat-" + selected.name)
        resolve_profile(load_catalog(path), selected.name, house, plan)
        assert check_lock(
            plan / "apizr.toml", plan / "apizr.plugins.lock.json", house
        ).valid
        if selected.name == profile:
            assert all(
                p.read_bytes() == (output / "plan" / p.relative_to(plan)).read_bytes()
                for p in plan.rglob("*")
                if p.is_file()
            )
    (output / "evidence.json").write_text(
        json.dumps(
            {
                "profiles": [p.name for p in profiles],
                "deterministic": True,
                "installed": False,
            }
        )
    )


def main_script():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument(
        "--plugin", action="append", required=True, help="NAME=REQUIREMENTS"
    )
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()
    prepare(
        args.wheelhouse,
        {
            name: Path(path)
            for name, path in (item.split("=", 1) for item in args.plugin)
        },
        args.commit,
        args.output,
        args.profile,
    )


if __name__ == "__main__":
    main_script()
