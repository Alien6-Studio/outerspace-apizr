"""Hold every public version surface to the declared release state.

scripts/docs_build.py:RELEASE_STATE is the single declaration of what is
published. The 0.4.5 publication shipped stale candidate wording to PyPI and
left forge defaults, the site navigation and the install recording behind
because nothing bound those surfaces to the declaration. These tests make the
release flip atomic: the change that declares a version stable must also move
every surface that names it, before any tag is cut.
"""

import re
import runpy
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
STATE = runpy.run_path(str(ROOT / "scripts/docs_build.py"))["RELEASE_STATE"]
STABLE = STATE["stable_release"]
TARGET = STATE["target_version"]

README = (ROOT / "README.md").read_text()
PACKAGING_READMES = {
    path.relative_to(ROOT).as_posix(): path.read_text()
    for path in [ROOT / "README.md", *sorted(ROOT.glob("plugins/*/README.md"))]
}
VERSIONED_SURFACES = {
    **PACKAGING_READMES,
    "mkdocs.yml": (ROOT / "mkdocs.yml").read_text(),
    "SECURITY.md": (ROOT / "SECURITY.md").read_text(),
    **{
        path.relative_to(ROOT).as_posix(): path.read_text()
        for path in sorted(ROOT.glob("docs/**/*.md"))
    },
}


def test_release_state_is_coherent():
    assert STATE["status"] in {"stable", "release-candidate"}
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
        "version"
    ]
    assert TARGET == version
    if STATE["status"] == "stable":
        assert STABLE == TARGET
    else:
        assert STABLE != TARGET


def test_forge_defaults_pin_the_declared_stable_release():
    action = yaml.safe_load((ROOT / "action.yml").read_text())
    assert action["inputs"]["apizr-version"]["default"] == STABLE
    header, _ = yaml.safe_load_all((ROOT / "templates/apizr.yml").read_text())
    assert header["spec"]["inputs"]["apizr-version"]["default"] == STABLE


def test_install_surfaces_follow_the_declared_stable_release():
    install = f"uv tool install outerspace-apizr=={STABLE}"
    assert install in README
    tape = (ROOT / "docs/assets/videos/uv-install.tape").read_text()
    assert install in tape
    # The recording must be referenced from master, never from a commit pinned
    # before the release flip.
    assert (
        "https://raw.githubusercontent.com/Alien6-Studio/outerspace-apizr/"
        "master/docs/assets/videos/uv-install.gif" in README
    )


def test_security_policy_names_the_current_line():
    major, minor, _ = STABLE.split(".")
    assert f"{major}.{minor}.x line" in (ROOT / "SECURITY.md").read_text()


def test_navigation_and_release_record_match_the_declaration():
    assert (ROOT / f"docs/releases/{TARGET}.md").is_file()
    nav = (ROOT / "mkdocs.yml").read_text()
    if STATE["status"] == "stable":
        assert f"- {STABLE}: releases/{STABLE}.md" in nav


def test_no_surface_still_calls_the_stable_release_a_candidate():
    pattern = re.compile(
        rf"{re.escape(STABLE)}\s+(?:release\s+)?candidate|"
        rf"candidate\s+\(?{re.escape(STABLE)}",
        re.IGNORECASE,
    )
    offenders = [
        f"{name}: {match.group(0)!r}"
        for name, text in VERSIONED_SURFACES.items()
        for match in [pattern.search(text)]
        if match
    ]
    assert not offenders, offenders


def test_packaging_readmes_never_deny_the_declared_publication():
    # These files become the immutable PyPI long descriptions at build time.
    pattern = re.compile(
        r"not yet (?:a )?published|not yet a release|prepublication candidate",
        re.IGNORECASE,
    )
    offenders = [
        f"{name}: {match.group(0)!r}"
        for name, text in PACKAGING_READMES.items()
        for match in [pattern.search(text)]
        if match
    ]
    if STATE["status"] == "stable":
        assert not offenders, offenders
