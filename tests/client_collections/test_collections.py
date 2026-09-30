"""Artifact-only semantics, parity, tamper refusal and recoverable publication."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml
from repository_interfaces.conftest import evidence

from apizr.capabilities.model import Digest
from apizr.client_collections import (
    ClientCollection,
    ClientError,
    canonical_bytes,
    collection_digest,
    export_client_collection,
    model,
    output,
    plan_client_collection,
    planner,
    publish_collection,
    render_client_collection,
    renderers,
)
from apizr.client_collections.model import (
    ClientExportManifest,
    logical_path,
    unique_json,
)
from apizr.client_collections.planner import example_value
from apizr.generators.rest import generate
from apizr.inspection import inspect_source
from apizr.interfaces.model import TypeSpec
from apizr.interfaces.schema import json_schema
from apizr.interfaces.serialization import json_bytes
from apizr.repository_interfaces.generator import render_repository_bundle

FORMATS = ("postman", "bruno", "insomnia")
SOURCE = b'''from typing import Literal
def echo(count: int, enabled: bool, words: list[str], mode: Literal["caf\\u00e9", "other"], choice: str | int, suffix: str = "default") -> str:
    """A deterministic fixture."""
    return str(count) + suffix
def total(values: list[float], extra: float = 1.5) -> float:
    return sum(values) + extra
'''


@pytest.fixture(params=("single", "repository"))
def bundle(tmp_path, request):
    path = tmp_path / "rest"
    if request.param == "single":
        generate(inspect_source(SOURCE, module_name="sample"), SOURCE, path)
    else:
        inputs = evidence(
            {"sample.py": SOURCE},
            selected=("python:sample:echo", "python:sample:total"),
        )
        files = render_repository_bundle(*inputs, interface="rest")
        path.mkdir()
        for name, content in files.items():
            p = path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
    return path


def tree(path):
    return {
        p.relative_to(path).as_posix(): p.read_bytes()
        for p in path.rglob("*")
        if p.is_file()
    }


def read_requests(files, format):
    if format == "postman":
        root = yaml.safe_load(files[".resources/definition.yaml"])
        requests = sorted(
            (
                yaml.safe_load(v)
                for p, v in files.items()
                if p.endswith(".request.yaml")
            ),
            key=lambda r: r["order"],
        )
        return root["variables"]["base_url"], [
            (
                r["name"],
                r["method"],
                r["url"].removeprefix("{{base_url}}"),
                json.loads(r["body"]["content"]),
                r["description"],
            )
            for r in requests
        ]
    if format == "bruno":
        root = yaml.safe_load(files["opencollection.yml"])
        requests = sorted(
            (yaml.safe_load(v) for p, v in files.items() if p.startswith("request-")),
            key=lambda r: r["info"]["seq"],
        )
        return root["request"]["variables"][0]["value"], [
            (
                r["info"]["name"],
                r["http"]["method"],
                r["http"]["url"].removeprefix("{{base_url}}"),
                json.loads(r["http"]["body"]["data"]),
                r["info"]["description"],
            )
            for r in requests
        ]
    root = yaml.safe_load(files["collection.yaml"])
    return root["environments"]["data"]["base_url"], [
        (
            r["name"],
            r["method"],
            r["url"].removeprefix("{{ _.base_url }}"),
            json.loads(r["body"]["text"]),
            r["meta"]["description"],
        )
        for r in root["collection"]
    ]


def test_ir_and_parity(bundle, tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET", "SENTINEL_MUST_NOT_APPEAR")
    collection = plan_client_collection(bundle, base_url="https://example.test/api/")
    assert collection.base_url == "https://example.test/api"
    assert collection_digest(collection) == Digest.of_bytes(canonical_bytes(collection))
    assert b"SENTINEL" not in canonical_bytes(collection)
    assert str(tmp_path).encode() not in canonical_bytes(collection)
    assert all(
        "suffix" not in r.example and "extra" not in r.example
        for r in collection.requests
    )
    for request in collection.requests:
        jsonschema.validate(request.example, request.request_schema)
    facts = []
    for format in FORMATS:
        files = render_client_collection(collection, format=format)
        assert files == render_client_collection(collection, format=format)
        facts.append(read_requests(files, format))
        manifest = ClientExportManifest.model_validate_json(files[model.MANIFEST])
        assert manifest.client_collection_digest == collection_digest(collection)
        assert manifest.source_manifest_digest == collection.source.manifest_digest
        assert {c for f in manifest.files for c in f.capability_ids} == {
            r.capability_id for r in collection.requests
        }
        assert all(Digest.of_bytes(files[f.path]) == f.digest for f in manifest.files)
    assert facts[0] == facts[1] == facts[2]
    assert [x[2] for x in facts[0][1]] == [r.route for r in collection.requests]
    copied = tmp_path / "another-checkout"
    shutil.copytree(bundle, copied)
    assert canonical_bytes(
        plan_client_collection(copied, base_url=collection.base_url)
    ) == canonical_bytes(collection)
    reordered = collection.model_dump(mode="json")
    reordered = dict(reversed(list(reordered.items())))
    assert canonical_bytes(
        ClientCollection.model_validate_json(json.dumps(reordered))
    ) == canonical_bytes(collection)


@pytest.mark.parametrize("format", FORMATS)
def test_export_sync(bundle, tmp_path, format):
    root = tmp_path / "clients"
    result = export_client_collection(bundle, format=format, output_dir=root)
    before = tree(root)
    assert result.state == "exported"
    assert (
        export_client_collection(
            bundle, format=format, output_dir=root, sync=True
        ).state
        == "synced"
    )
    assert tree(root) == before
    changed = plan_client_collection(
        bundle, name="Updated", base_url="https://example.test"
    )
    publish_collection(changed, format=format, output_dir=root, sync=True)
    assert tree(root) == render_client_collection(changed, format=format)
    with pytest.raises(ClientError, match="client_output_not_empty"):
        publish_collection(changed, format=format, output_dir=root)


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("edit", "modified"),
        ("unknown", "conflict"),
        ("missing", "invalid"),
        ("corrupt", "invalid"),
        ("hash", "modified"),
        ("format", "conflict"),
        ("directory", "conflict"),
        ("symlink", "conflict"),
        ("hardlink", "conflict"),
    ],
)
def test_sync_refusal(bundle, tmp_path, mutation, code):
    root = tmp_path / "clients"
    export_client_collection(bundle, format="postman", output_dir=root)
    request = next(root.glob("*.yaml"))
    manifest = root / model.MANIFEST
    if mutation == "edit":
        request.write_text("edited")
    elif mutation == "unknown":
        (root / "notes.txt").write_text("user")
    elif mutation == "missing":
        manifest.unlink()
    elif mutation == "corrupt":
        manifest.write_text('{"x":1,"x":2}')
    elif mutation == "hash":
        d = json.loads(manifest.read_bytes())
        d["files"][0]["digest"]["value"] = "0" * 64
        manifest.write_bytes(json_bytes(d))
    elif mutation == "directory":
        (root / "empty").mkdir()
    elif mutation == "symlink":
        (root / "link").symlink_to(request)
    elif mutation == "hardlink":
        os.link(request, root / "link")
    before = tree(root)
    with pytest.raises(ClientError, match=code):
        export_client_collection(
            bundle,
            format="bruno" if mutation == "format" else "postman",
            output_dir=root,
            sync=True,
        )
    assert tree(root) == before


@pytest.mark.parametrize("phase", ("write", "rename"))
def test_interruption_preserves_previous(bundle, tmp_path, monkeypatch, phase):
    root = tmp_path / "clients"
    export_client_collection(bundle, format="bruno", output_dir=root)
    before = tree(root)
    if phase == "write":

        def interrupt(*args):
            raise KeyboardInterrupt

        monkeypatch.setattr(output, "_write", interrupt)
    else:
        rename = os.rename

        def interrupt(src, dst, **kwargs):
            if src.endswith(".stage"):
                raise KeyboardInterrupt
            return rename(src, dst, **kwargs)

        monkeypatch.setattr(output.os, "rename", interrupt)
    with pytest.raises(KeyboardInterrupt):
        export_client_collection(
            bundle, format="bruno", output_dir=root, sync=True, name="new"
        )
    assert tree(root) == before
    assert not list(tmp_path.glob(".apizr-clients-*"))


@pytest.mark.parametrize(
    "mutation",
    (
        "openapi",
        "missing",
        "method",
        "route",
        "duplicate",
        "extra",
        "malformed",
        "utf8",
        "duplicate-key",
        "symlink",
        "parent-symlink",
        "special",
        "path",
        "identity",
        "manifest-symlink",
    ),
)
def test_bundle_tamper(bundle, tmp_path, mutation):
    manifest = next(bundle.glob("apizr*rest.json"))
    data = json.loads(manifest.read_bytes())
    endpoints = data.get("endpoints", data.get("capabilities"))
    if mutation == "openapi":
        (bundle / "openapi.json").write_text("{}")
    elif mutation == "missing":
        (bundle / "openapi.json").unlink()
    elif mutation == "method":
        endpoints[0]["method"] = "GET"
    elif mutation == "route":
        endpoints[0]["route"] = "/capabilities/changed"
    elif mutation == "duplicate":
        endpoints.append(endpoints[0])
    elif mutation == "extra":
        data["unrecognized"] = True
    elif mutation == "path":
        data["artifacts"]["../outside"] = data["artifacts"]["openapi.json"]
    elif mutation == "identity":
        data["repository_interface_digest" if "endpoints" in data else "ir_digest"][
            "value"
        ] = "0" * 64
    elif mutation in ("symlink", "special"):
        p = bundle / "openapi.json"
        p.unlink()
        if mutation == "symlink":
            p.symlink_to(tmp_path / "outside")
        else:
            os.mkfifo(p)
    elif mutation == "parent-symlink":
        target = tmp_path / "real"
        bundle.rename(target)
        bundle.symlink_to(target, target_is_directory=True)
    if mutation == "malformed":
        manifest.write_text("{")
    elif mutation == "utf8":
        manifest.write_bytes(b"\xff")
    elif mutation == "duplicate-key":
        manifest.write_text('{"a":1,"a":2}')
    elif mutation == "manifest-symlink":
        target = tmp_path / "original.json"
        manifest.rename(target)
        manifest.symlink_to(target)
    elif mutation not in ("parent-symlink",):
        manifest.write_bytes(json_bytes(data))
    with pytest.raises(ClientError):
        export_client_collection(bundle, format="bruno", output_dir=tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("name", ("", "\n", "a\x00", "x" * 257, "\ud800"))
def test_bad_name(bundle, name):
    with pytest.raises(ClientError, match="client_name_invalid"):
        plan_client_collection(bundle, name=name)


@pytest.mark.parametrize(
    "url",
    (
        "ftp://example.test",
        "http://u:p@localhost",
        "http://u@localhost",
        "http://localhost?",
        "http://localhost#",
        "http://localhost\n",
        "http://",
        "http://localhost:0",
        "http://localhost:99999",
        "http://{{secret}}",
        "http://local host",
        "http://localhost/" + "x" * 2048,
    ),
)
def test_bad_url(bundle, url):
    with pytest.raises(ClientError, match="client_base_url_invalid"):
        plan_client_collection(bundle, base_url=url)


@pytest.mark.parametrize(
    "kind",
    (
        "any",
        "int",
        "str",
        "float",
        "bool",
        "null",
        "list",
        "dict",
        "tuple",
        "set",
        "union",
        "literal",
    ),
)
def test_examples(kind):
    spec = TypeSpec.model_validate(
        {
            "kind": kind,
            **(
                {"items": [{"kind": "int"}]}
                if kind in ("list", "dict", "tuple", "set", "union")
                else {}
            ),
            **({"values": ["café", "other"]} if kind == "literal" else {}),
        }
    )
    jsonschema.validate(example_value(spec), json_schema(spec))


def test_nested_and_ordered_examples():
    specs = [
        TypeSpec(kind="tuple", items=(TypeSpec(kind="str"), TypeSpec(kind="bool"))),
        TypeSpec(kind="tuple", variadic=True, items=(TypeSpec(kind="int"),)),
        TypeSpec(kind="union", items=(TypeSpec(kind="null"), TypeSpec(kind="str"))),
        TypeSpec(
            kind="tuple",
            items=(
                TypeSpec(
                    kind="list",
                    items=(TypeSpec(kind="dict", items=(TypeSpec(kind="int"),)),),
                ),
            ),
        ),
    ]
    assert [example_value(s) for s in specs] == [["", False], [], None, [[]]]
    for s in specs:
        jsonschema.validate(example_value(s), json_schema(s))
    with pytest.raises(ClientError):
        example_value(TypeSpec(kind="literal"))
    with pytest.raises(ClientError):
        example_value(TypeSpec(kind="union"))
    with pytest.raises(ClientError):
        example_value(TypeSpec(kind="int"), depth=33)


@pytest.mark.parametrize(
    "path",
    ("../x", "/x", "a/../x", "a//x", "a\\x", "a\x00", "a.", " a", "", "x" * 129, "x:"),
)
def test_unsafe_paths(path):
    with pytest.raises(ValueError):
        logical_path(path)


def test_collisions_and_unicode(bundle):
    c = plan_client_collection(bundle)
    names = ("echo", "ECHO", "écho", "CON", "NUL", "世界")
    requests = tuple(
        c.requests[0].model_copy(
            update={
                "name": name,
                "capability_id": f"python:sample:{name}",
                "route": "/capabilities/" + name,
            }
        )
        for name in names
    )
    c = c.model_copy(update={"requests": requests})
    paths = renderers.request_names(c)
    assert len({p.casefold() for p in paths}) == len(names)
    assert paths == renderers.request_names(c)
    for f in FORMATS:
        assert len(read_requests(render_client_collection(c, format=f), f)[1]) == len(
            names
        )


def test_bounds_and_unknown_format(bundle, monkeypatch):
    c = plan_client_collection(bundle)
    with pytest.raises(ClientError, match="unsupported"):
        render_client_collection(c, format="unknown")
    monkeypatch.setattr(renderers, "MAX_FILE", 5)
    with pytest.raises(ClientError, match="too_large"):
        render_client_collection(c, format="postman")
    monkeypatch.setattr(planner, "MAX_REQUESTS", 1)
    with pytest.raises(ClientError, match="too_large"):
        plan_client_collection(bundle)


def test_empty_absent_unsafe_and_recovery(bundle, tmp_path):
    c = plan_client_collection(bundle)
    root = tmp_path / "out"
    root.mkdir()
    publish_collection(c, format="insomnia", output_dir=root)
    with pytest.raises(ClientError):
        publish_collection(
            c, format="insomnia", output_dir=tmp_path / "missing", sync=True
        )
    link = tmp_path / "link"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(ClientError):
        publish_collection(c, format="insomnia", output_dir=link, sync=True)
    for p in (tmp_path / "missing-parent" / "out", tmp_path / ".." / "out", Path("/")):
        with pytest.raises(ClientError):
            publish_collection(c, format="insomnia", output_dir=p)
    stem = ".apizr-clients-" + hashlib.sha256(b"out").hexdigest()[:20]
    (tmp_path / (stem + ".backup")).mkdir()
    with pytest.raises(ClientError, match="conflict"):
        publish_collection(c, format="insomnia", output_dir=root, sync=True)


def test_duplicate_json():
    for data in (b'{"a":1,"a":2}', b'{"a":NaN}', b'"\xff"'):
        with pytest.raises(ValueError):
            unique_json(data)


def test_cli_and_separate_process_determinism(bundle, tmp_path):
    roots = [tmp_path / "one", tmp_path / "two"]
    for p in roots:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "apizr.cli",
                "clients",
                "export",
                "--bundle",
                str(bundle),
                "--format",
                "bruno",
                "--output-dir",
                str(p),
            ],
            capture_output=True,
            check=True,
        )
        assert json.loads(result.stdout)["state"] == "exported"
    assert tree(roots[0]) == tree(roots[1])
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from apizr.cli import main; raise SystemExit(main())",
            "clients",
            "export",
            "--bundle",
            str(bundle),
            "--format",
            "bruno",
            "--output-dir",
            str(roots[0]),
        ],
        capture_output=True,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout)["diagnostic"] == "client_output_not_empty"


def test_lazy_extra(bundle, monkeypatch):
    c = plan_client_collection(bundle)
    monkeypatch.setitem(sys.modules, "yaml", None)
    assert canonical_bytes(c)
    with pytest.raises(ClientError, match="clients_extra_required"):
        render_client_collection(c, format="postman")


def test_cli_refusal_and_cancellation(bundle, tmp_path, capsys, monkeypatch):
    from apizr import clients_cli

    args = [
        "export",
        "--bundle",
        str(bundle),
        "--format",
        "bruno",
        "--output-dir",
        str(tmp_path / "out"),
    ]
    assert clients_cli.main(args + ["--name", ""]) == 2
    assert json.loads(capsys.readouterr().out)["diagnostic"] == "client_name_invalid"

    def cancel(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(clients_cli, "export_client_collection", cancel)
    assert clients_cli.main(args) == 130


def test_changed_bundle_sync(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    for path, value in ((first, 1), (second, 2)):
        source = f"def call(x: int = {value}) -> int:\n    return x\n".encode()
        generate(inspect_source(source, module_name="sample"), source, path)
    out = tmp_path / "clients"
    export_client_collection(first, format="postman", output_dir=out)
    before = tree(out)
    export_client_collection(second, format="postman", output_dir=out, sync=True)
    assert tree(out) != before
    assert tree(out) == render_client_collection(
        plan_client_collection(second), format="postman"
    )


def test_fixed_cross_platform_golden(tmp_path):
    source = (
        b'def echo(value: int, suffix: str = "default") -> int:\n    return value\n'
    )
    generate(inspect_source(source, module_name="portable"), source, tmp_path / "rest")
    collection = plan_client_collection(tmp_path / "rest")
    actual = {
        format: {
            path: hashlib.sha256(content).hexdigest()
            for path, content in render_client_collection(
                collection, format=format
            ).items()
        }
        for format in FORMATS
    }
    expected = json.loads(
        (
            Path(__file__).parents[1] / "fixtures/client-collections/sha256.json"
        ).read_text()
    )
    assert actual == expected


def test_required_artifact_and_rehashed_route(bundle, tmp_path):
    manifest_path = next(bundle.glob("apizr*rest.json"))
    manifest = json.loads(manifest_path.read_bytes())
    manifest["artifacts"].pop("app.py")
    manifest_path.write_bytes(json_bytes(manifest))
    with pytest.raises(ClientError, match="rest_bundle_invalid"):
        plan_client_collection(bundle)


def test_no_analysis_or_execution(bundle, monkeypatch):
    import apizr.exposure
    import apizr.inspection
    import apizr.readiness
    import apizr.repository

    def forbidden(*args, **kwargs):
        raise AssertionError("source analysis/execution is forbidden")

    monkeypatch.setattr(apizr.inspection, "inspect_source", forbidden)
    monkeypatch.setattr(apizr.readiness, "assess", forbidden)
    monkeypatch.setattr(apizr.exposure, "plan_exposure", forbidden)
    monkeypatch.setattr(apizr.repository, "scan_sources", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    assert plan_client_collection(bundle)
