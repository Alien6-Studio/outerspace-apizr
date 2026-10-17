"""Reproducible source-including VSIX and exact Node dependency/notice inventory."""

import argparse
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXTENSION = ROOT / "editors/vscode"
VSX = "http://schemas.microsoft.com/developer/vsx-schema/2011"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def audit():
    policy = json.loads((ROOT / "policy/vscode-dependencies.json").read_bytes())
    lock = json.loads((EXTENSION / "package-lock.json").read_bytes())
    package = json.loads((EXTENSION / "package.json").read_bytes())
    assert not package.get("dependencies")
    assert set(lock["packages"]) - {""} == set(policy["packages"])
    checked = {}
    for key, expected in policy["packages"].items():
        admitted = lock["packages"][key]
        installed = json.loads((EXTENSION / key / "package.json").read_bytes())
        for field in ("version", "license", "integrity"):
            assert admitted[field] == expected[field], (key, field)
        assert installed["version"] == expected["version"]
        assert installed["license"] == expected["license"]
        for filename, sha in expected["license_files"].items():
            assert digest((EXTENSION / key / filename).read_bytes()) == sha
        checked[key] = expected
    return {"result": "pass", "runtime_dependencies": 0, "packages": checked}


def manifest(package):
    ET.register_namespace("", VSX)

    def child(parent, tag, attributes=None, text=None):
        element = ET.SubElement(parent, "{" + VSX + "}" + tag, attributes or {})
        element.text = text
        return element

    root = ET.Element("{" + VSX + "}PackageManifest", {"Version": "2.0.0"})
    metadata = child(root, "Metadata")
    child(
        metadata,
        "Identity",
        {
            "Language": "en-US",
            "Id": package["name"],
            "Version": package["version"],
            "Publisher": package["publisher"],
        },
    )
    for tag, text in (
        ("DisplayName", package["displayName"]),
        ("Description", package["description"]),
        ("Categories", ",".join(package["categories"])),
        ("GalleryFlags", "Public"),
        ("License", "extension/LICENSE"),
        ("Icon", "extension/" + package["icon"]),
    ):
        child(metadata, tag, text=text)
    properties = child(metadata, "Properties")
    for name, value in (
        ("Microsoft.VisualStudio.Code.Engine", package["engines"]["vscode"]),
        ("Microsoft.VisualStudio.Code.ExtensionKind", "workspace"),
        ("Microsoft.VisualStudio.Code.ExecutesCode", "true"),
        ("Microsoft.VisualStudio.Services.Links.Source", package["repository"]["url"]),
        ("Microsoft.VisualStudio.Services.Content.Pricing", "Free"),
    ):
        child(properties, "Property", {"Id": name, "Value": value})
    child(
        child(root, "Installation"),
        "InstallationTarget",
        {"Id": "Microsoft.VisualStudio.Code"},
    )
    child(root, "Dependencies")
    assets = child(root, "Assets")
    for kind, filename in (
        ("Microsoft.VisualStudio.Code.Manifest", "package.json"),
        ("Microsoft.VisualStudio.Services.Content.Details", "README.md"),
        ("Microsoft.VisualStudio.Services.Content.License", "LICENSE"),
        ("Microsoft.VisualStudio.Services.Icons.Default", package["icon"]),
    ):
        child(
            assets,
            "Asset",
            {"Type": kind, "Path": "extension/" + filename, "Addressable": "true"},
        )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def build(output, version=None):
    package = json.loads((EXTENSION / "package.json").read_bytes())
    if version is not None:
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
            raise ValueError("Invalid qualification fixture version")
        package["version"] = version
    payload = {
        "extension/package.json": (json.dumps(package, indent=2) + "\n").encode(),
        "extension/LICENSE": (ROOT / "LICENSE").read_bytes(),
    }
    for filename in (
        "README.md",
        "package-lock.json",
        "tsconfig.json",
        "media/icon.png",
    ):
        payload["extension/" + filename] = (EXTENSION / filename).read_bytes()
    sources = sorted((EXTENSION / "src").glob("*.ts"))
    assert sources and {p.stem for p in sources} == {
        p.stem for p in (EXTENSION / "out").glob("*.js")
    }
    for source in sources:
        for path in (source, EXTENSION / "out" / (source.stem + ".js")):
            assert not path.is_symlink()
            payload["extension/" + path.relative_to(EXTENSION).as_posix()] = (
                path.read_bytes()
            )
    payload["extension.vsixmanifest"] = manifest(package)
    payload["[Content_Types].xml"] = (
        b'<?xml version="1.0" encoding="utf-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension=".json" ContentType="application/json"/><Default Extension=".js" ContentType="application/javascript"/><Default Extension=".ts" ContentType="text/plain"/><Default Extension=".md" ContentType="text/markdown"/><Default Extension=".png" ContentType="image/png"/><Default Extension=".vsixmanifest" ContentType="text/xml"/></Types>\n'
    )
    path = output / f"apizr-{package['version']}.vsix"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(payload.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    return path, {name: digest(raw) for name, raw in sorted(payload.items())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture-version")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Local development proof only; CI requires a clean checkout",
    )
    args = parser.parse_args()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()
    )
    if dirty and not args.allow_dirty:
        raise ValueError(
            "A retained VSIX requires a clean source; use --allow-dirty only for development"
        )
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    licenses = audit()
    (output / "dependency-licenses.json").write_text(
        json.dumps(licenses, indent=2) + "\n"
    )
    compiler = [
        "node",
        str(EXTENSION / "node_modules/typescript/bin/tsc"),
        "-p",
        str(EXTENSION),
    ]
    subprocess.run(compiler, cwd=ROOT, check=True)
    path, files = build(output, args.fixture_version)
    first = path.read_bytes()
    subprocess.run(compiler, cwd=ROOT, check=True)
    build(output, args.fixture_version)
    assert path.read_bytes() == first
    proof = {
        "schema_version": "apizr.vscode-build/v1",
        "result": "pass",
        "vsix": path.name,
        "sha256": digest(first),
        "files": files,
        "repeated_build_identical": True,
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        "npm": subprocess.check_output(["npm", "--version"], text=True).strip(),
        "typescript": "5.9.3",
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "qualification_fixture": args.fixture_version is not None,
        "source_dirty": dirty,
    }
    (output / (path.stem + ".json")).write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps({"result": "pass", "vsix": str(path), "sha256": proof["sha256"]}))


if __name__ == "__main__":
    main()
