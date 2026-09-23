"""Prepare a private local Homebrew test tap; never publish it or install implicitly."""

import argparse
import hashlib
import json
import subprocess
import tarfile
import tomllib
import urllib.request
from pathlib import Path

from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename
from smoke_extension_packaging import REPO, require_uv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", type=Path, help="New directory outside checkout")
    args = parser.parse_args()
    uv = require_uv()
    root = args.work_dir.resolve()
    if root.is_relative_to(REPO) or REPO.is_relative_to(root):
        parser.error("Use a new directory outside checkout")
    root.mkdir(parents=True, exist_ok=False)
    source = root / "source"
    wheels = source / "wheels"
    wheels.mkdir(parents=True)
    subprocess.run(
        [uv, "build", "--wheel", str(REPO), "--out-dir", str(wheels)], check=True
    )
    lock = tomllib.loads((REPO / "uv.lock").read_text())
    tags = set(sys_tags())
    names = {
        "pydantic",
        "pydantic-core",
        "annotated-types",
        "typing-extensions",
        "typing-inspection",
    }
    downloaded = []
    for package in lock["package"]:
        if package["name"] not in names:
            continue
        for wheel in package["wheels"]:
            filename = wheel["url"].rsplit("/", 1)[1]
            if not (parse_wheel_filename(filename)[3] & tags):
                continue
            if not wheel["url"].startswith("https://files.pythonhosted.org/"):
                raise RuntimeError("Unexpected dependency source")
            with urllib.request.urlopen(wheel["url"], timeout=60) as response:
                data = response.read()
            if "sha256:" + hashlib.sha256(data).hexdigest() != wheel["hash"]:
                raise RuntimeError("Dependency hash mismatch")
            (wheels / filename).write_bytes(data)
            downloaded.append(
                {"name": package["name"], "url": wheel["url"], "hash": wheel["hash"]}
            )
            break
        else:
            raise RuntimeError(f"No compatible locked wheel for {package['name']}")
    if {item["name"] for item in downloaded} != names:
        raise RuntimeError("Base dependency set changed; review formula preparation")
    archive = root / "apizr-v04-probe.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        output.add(source, arcname="apizr-v04-probe")
    tap = root / "tap"
    formula_dir = tap / "Formula"
    formula_dir.mkdir(parents=True)
    formula = f'''class ApizrV04Probe < Formula
  desc "Local-only Apizr V04-01 packaging qualification"
  homepage "https://github.com/Alien6-Studio/outerspace-apizr"
  url {json.dumps(archive.as_uri())}
  version "0.3.0"
  sha256 "{hashlib.sha256(archive.read_bytes()).hexdigest()}"
  license "GPL-3.0-or-later"

  depends_on "python@3.14"
  depends_on "uv" => :build

  def install
    system Formula["python@3.14"].opt_bin/"python3.14", "-m", "venv", "--without-pip", libexec
    system Formula["uv"].opt_bin/"uv", "--no-cache", "--offline", "pip", "install",
           "--python", libexec/"bin/python", "--no-index", "--find-links", buildpath/"wheels",
           Dir["wheels/outerspace_apizr-*.whl"].first
    bin.install_symlink (libexec/"bin/apizr") => name
  end

  test do
    assert_match "outerspace-apizr 0.3.0", shell_output("#{{bin}}/apizr-v04-probe --version")
  end
end
'''
    (formula_dir / "apizr-v04-probe.rb").write_text(formula)
    (root / "dependency-evidence.json").write_text(
        json.dumps(downloaded, indent=2) + "\n"
    )
    subprocess.run(["git", "init", str(tap)], check=True)
    subprocess.run(["git", "-C", str(tap), "add", "Formula"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tap),
            "commit",
            "-s",
            "-m",
            "test: local-only Apizr packaging formula",
        ],
        check=True,
    )
    print(f"Prepared private test tap: {tap}")
    print(f"HOMEBREW_NO_AUTO_UPDATE=1 brew tap apizr-v04/prototype {tap.as_uri()}")
    print(
        "HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 brew install --ignore-dependencies --build-from-source apizr-v04/prototype/apizr-v04-probe"
    )
    print("HOMEBREW_DEVELOPER=1 brew test apizr-v04/prototype/apizr-v04-probe")


if __name__ == "__main__":
    main()
