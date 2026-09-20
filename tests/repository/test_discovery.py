import os
import shutil
from pathlib import Path

import pytest

from apizr.repository import (
    Code,
    ScanError,
    ScanPolicy,
    catalog_bytes,
    discovery,
    scan,
    scan_sources,
    scanner,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/catalog"


def write(root, path, data=b"def f(): return 1"):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def test_empty_projects_and_invalid_sources_continue(tmp_path):
    empty = scan(tmp_path)
    assert empty.exit_code == 0 and empty.statistics.sources == 0
    catalog = scan(FIXTURES / "invalid")
    assert len(catalog.sources) == 2 and len(catalog.capabilities) == 1
    assert catalog.diagnostics[0].code == Code.PARSE
    assert catalog.diagnostics[0].line == 1
    assert catalog.exit_code == 1
    names = scan(FIXTURES / "names")
    assert any(c.module == "λ" for c in names.capabilities)
    assert names.diagnostics[0].code == Code.MODULE
    for number, raw in enumerate(
        [
            b"# coding: made-up\ndef f(): pass",
            b"# coding: ascii\n# \xff\ndef f(): pass",
            b"def f():\n secret-value-123 $$$",
        ]
    ):
        write(tmp_path, f"bad{number}.py", raw)
    write(tmp_path, "good.py")
    result = scan(tmp_path)
    assert len(result.capabilities) == 1
    assert len(result.diagnostics) == 3
    assert all(d.code in {Code.PARSE, Code.ENCODING} for d in result.diagnostics)
    assert b"secret-value" not in catalog_bytes(result)
    assert str(tmp_path).encode() not in catalog_bytes(result)


def test_default_exclusions_do_not_hide_tests_or_require_git(tmp_path):
    write(tmp_path, "tests/test_unit.py")
    write(tmp_path, "ordinary.py")
    for name in ScanPolicy().excluded_directories:
        write(tmp_path, f"{name}/hidden.py")
    assert len(scan(tmp_path).sources) == 2
    explicit = scan(
        tmp_path,
        policy=ScanPolicy(
            excluded_directories=(*ScanPolicy().excluded_directories, "tests")
        ),
    )
    assert [s.path for s in explicit.sources] == ["ordinary.py"]
    assert (
        scan_sources(
            [("readme.txt", b"not Python"), ("tests/test_unit.py", b"def f(): pass")]
        ).statistics.sources
        == 1
    )


def test_symlinks_are_never_followed_including_loops_and_roots(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    outside = write(tmp_path, "outside.py", b"def stolen(): pass")
    (repository / "file.py").symlink_to(outside)
    (repository / "loop").symlink_to(repository, target_is_directory=True)
    (repository / "outside").symlink_to(tmp_path, target_is_directory=True)
    result = scan(repository)
    assert not result.sources and not result.capabilities
    assert len(result.diagnostics) == 3
    assert all(d.code == Code.SYMLINK for d in result.diagnostics)
    assert result.exit_code == 0
    assert str(tmp_path).encode() not in catalog_bytes(result)
    missing = scan(repository, policy=ScanPolicy(source_roots=("missing", "outside")))
    assert [d.code for d in missing.diagnostics] == [Code.ROOT, Code.ROOT]
    assert missing.exit_code == 1
    alias = tmp_path / "alias"
    alias.symlink_to(repository, target_is_directory=True)
    with pytest.raises(ScanError):
        scan(alias)
    with pytest.raises(ScanError):
        scan(tmp_path / "missing")
    with pytest.raises(ScanError):
        scan(outside)


@pytest.mark.parametrize(
    "change,limit",
    [
        ({"max_source_files": 1}, "sources"),
        ({"max_total_bytes": 5}, "bytes"),
        ({"max_entries": 1}, "entries"),
        ({"max_depth": 1}, "depth"),
    ],
)
def test_global_bounds_discard_partial_prefix(tmp_path, change, limit):
    write(tmp_path, "a.py")
    write(tmp_path, "b/c/d.py")
    result = scan(tmp_path, policy=ScanPolicy(**change))
    assert not result.sources and not result.capabilities
    assert result.diagnostics[0].code == Code.LIMIT
    assert result.diagnostics[0].limit == limit
    assert result.exit_code == 1


def test_large_file_not_read_and_independent_source_survives(tmp_path):
    huge = tmp_path / "huge.py"
    with huge.open("wb") as stream:
        stream.truncate(2**30)
    write(tmp_path, "good.py")
    result = scan(tmp_path)
    assert result.statistics.inspected_sources == 1
    source = next(s for s in result.sources if s.path == "huge.py")
    assert source.size == 2**30 and source.source_digest is None
    assert result.diagnostics[0].code == Code.SIZE
    memory = scan_sources(
        [("huge.py", b"x" * 30), ("good.py", b"pass")],
        policy=ScanPolicy(max_file_bytes=20),
    )
    assert memory.diagnostics[0].code == Code.SIZE


def test_manifest_bounds_stop_consumption_and_reject_duplicate_paths():
    def sources():
        yield "a.py", b"pass"
        yield "b.py", b"pass"
        raise AssertionError("Iterator consumed beyond limit")

    for policy in [
        ScanPolicy(max_source_files=1),
        ScanPolicy(max_entries=1),
        ScanPolicy(max_total_bytes=4),
    ]:
        catalog = scan_sources(sources(), policy=policy)
        assert not catalog.sources and catalog.diagnostics[0].code == Code.LIMIT
    with pytest.raises(ScanError, match="duplicate"):
        scan_sources([("a.py", b"pass"), ("./a.py", b"pass")])
    with pytest.raises(ValueError):
        scan_sources([("../outside.py", b"pass")])
    with pytest.raises(ScanError, match="unselected"):
        scanner.assemble(
            [discovery.SourceInput("readme.txt", b"pass", 4)], ScanPolicy()
        )


@pytest.mark.timeout(10)
@pytest.mark.parametrize("target", ["source", "directory", "fifo"])
def test_swap_to_external_symlink_before_open_is_contained(
    tmp_path, monkeypatch, target
):
    root = tmp_path / "repo"
    write(root, "a.py")
    write(root, "package/b.py")
    outside = write(tmp_path, "elsewhere/stolen.py", b"def stolen(): pass")
    original = os.open
    replaced = False
    name = "package" if target == "directory" else "a.py"

    def open_guard(path, flags, *args, **kwargs):
        nonlocal replaced
        if path == name and kwargs.get("dir_fd") is not None and not replaced:
            replaced = True
            victim = root / name
            if victim.is_dir():
                shutil.rmtree(victim)
            else:
                victim.unlink()
            if target == "fifo":
                os.mkfifo(victim)
            else:
                victim.symlink_to(
                    outside if target == "source" else outside.parent,
                    target_is_directory=target == "directory",
                )
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", open_guard)
    result = scan(root)
    assert replaced and result.exit_code == 1
    assert all("stolen" not in c.id for c in result.capabilities)
    assert any(d.code == Code.READ for d in result.diagnostics)


def test_unreadable_sources_directories_and_nonregular_files(tmp_path, monkeypatch):
    write(tmp_path, "denied.py")
    write(tmp_path, "hidden/other.py")
    write(tmp_path, "good.py")
    original_open = os.open

    def deny(path, flags, *args, **kwargs):
        if path == "denied.py":
            raise PermissionError("private host path must not leak")
        return original_open(path, flags, *args, **kwargs)

    original_scandir = os.scandir

    def denied_directory(path):
        if (
            isinstance(path, int)
            and os.fstat(path).st_ino == (tmp_path / "hidden").stat().st_ino
        ):
            raise PermissionError("private host path must not leak")
        return original_scandir(path)

    monkeypatch.setattr(os, "open", deny)
    monkeypatch.setattr(os, "scandir", denied_directory)
    os.mkfifo(tmp_path / "pipe.py")
    result = scan(tmp_path)
    assert len(result.capabilities) == 1
    assert len(result.diagnostics) == 3
    assert all(d.code == Code.READ for d in result.diagnostics)
    assert b"private host path" not in catalog_bytes(result)


@pytest.mark.parametrize(
    "error,code",
    [
        (RecursionError(), Code.ANALYSIS),
        (ValueError("HOST_PRIVATE_DETAIL_734"), Code.PARSE),
        (LookupError("HOST_PRIVATE_DETAIL_734"), Code.ENCODING),
    ],
)
def test_parser_failures_are_sanitized_and_local(monkeypatch, error, code):
    original = scanner.inspect_source

    def inspect(raw, *, module_name):
        if module_name == "bad":
            raise error
        return original(raw, module_name=module_name)

    monkeypatch.setattr(scanner, "inspect_source", inspect)
    catalog = scan_sources([("bad.py", b"pass"), ("good.py", b"def f(): return 1")])
    assert len(catalog.capabilities) == 1 and catalog.diagnostics[0].code == code
    assert b"HOST_PRIVATE_DETAIL_734" not in catalog_bytes(catalog)


@pytest.mark.parametrize("change", [b"changed but bounded", b"x" * 100])
def test_concurrent_source_mutation_does_not_get_a_trusted_digest(
    tmp_path, monkeypatch, change
):
    target = write(tmp_path, "moving.py", b"pass")
    original = os.fdopen

    class ChangingStream:
        def __init__(self, descriptor, *args):
            self.stream = original(descriptor, *args)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            target.write_bytes(change)
            return self.stream.read(size)

    monkeypatch.setattr(os, "fdopen", ChangingStream)
    result = scan(tmp_path, policy=ScanPolicy(max_file_bytes=32))
    assert result.sources[0].source_digest is None
    assert result.exit_code == 1
    assert result.diagnostics[0].code in {Code.READ, Code.SIZE}


def test_noncanonical_filesystem_name_is_diagnosed(tmp_path):
    write(tmp_path, "bad\\name.py")
    write(tmp_path, "good.py")
    result = scan(tmp_path)
    assert len(result.capabilities) == 1
    assert result.diagnostics[0].code == Code.MODULE
    assert result.diagnostics[0].path == "."


def test_non_utf8_filesystem_name_is_diagnosed_when_supported(tmp_path):
    name = os.fsencode(tmp_path) + b"/bad\xff.py"
    try:
        descriptor = os.open(name, os.O_CREAT | os.O_WRONLY, 0o600)
    except OSError:
        pytest.skip("Filesystem does not permit non-UTF-8 names")
    os.close(descriptor)
    write(tmp_path, "good.py")
    result = scan(tmp_path)
    assert len(result.capabilities) == 1
    assert result.diagnostics[0].code == Code.READ
    assert result.diagnostics[0].path == "."
