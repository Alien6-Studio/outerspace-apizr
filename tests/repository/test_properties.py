import shutil
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.repository import (
    ScanPolicy,
    catalog_bytes,
    catalog_digest,
    scan,
    scan_sources,
)


@settings(max_examples=12, deadline=None)
@given(st.lists(st.integers(-100, 100), min_size=1, max_size=6, unique=True), st.data())
def test_manifest_order_and_source_change_identity(values, data):
    files = [
        (f"package/module{i}.py", f"def run(): return {value}\n".encode())
        for i, value in enumerate(values)
    ]
    order = data.draw(st.permutations(files))
    original = scan_sources(files)
    assert catalog_bytes(original) == catalog_bytes(scan_sources(order))
    changed = scan_sources([(files[0][0], files[0][1] + b"# changed\n"), *files[1:]])
    assert original.sources[0].source_digest != changed.sources[0].source_digest
    assert original.repository_digest != changed.repository_digest
    assert catalog_digest(original) != catalog_digest(changed)
    assert [c.id for c in original.capabilities] == [c.id for c in changed.capabilities]
    assert original.sources[1:] == changed.sources[1:]


@settings(max_examples=6, deadline=None)
@given(st.integers(-100, 100))
def test_location_independence_and_excluded_content(value):
    import tempfile

    with tempfile.TemporaryDirectory() as left, tempfile.TemporaryDirectory() as right:
        first = Path(left) / "unrelated"
        second = Path(right) / "elsewhere"
        first.mkdir()
        (first / "api.py").write_text(f"def f(): return {value}\n")
        (first / ".git").mkdir()
        (first / ".git/hidden.py").write_text("this is invalid")
        shutil.copytree(first, second)
        (second / ".git/hidden.py").write_text("entirely different")
        a, b = scan(first), scan(second)
        assert catalog_bytes(a) == catalog_bytes(b)
        assert str(first).encode() not in catalog_bytes(a)
        (second / "api.py").rename(second / "moved.py")
        c = scan(second)
        assert a.capabilities[0].id != c.capabilities[0].id
        assert a.sources[0].source_digest == c.sources[0].source_digest


def test_filesystem_enumeration_order_cannot_change_catalog(tmp_path, monkeypatch):
    import os

    for name in ["b", "a"]:
        (tmp_path / name).mkdir()
        for file in ["b.py", "a.py"]:
            (tmp_path / name / file).write_text("def f(): pass")
    before = scan(tmp_path)
    original = os.scandir

    class Reverse:
        def __init__(self, path):
            with original(path) as entries:
                self.entries = list(entries)[::-1]

        def __enter__(self):
            return iter(self.entries)

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(os, "scandir", Reverse)
    assert catalog_bytes(scan(tmp_path)) == catalog_bytes(before)


def test_source_root_order_is_irrelevant_and_policy_is_bound():
    files = [("src/a.py", b"def f(): pass"), ("tools/b.py", b"def g(): pass")]
    a = scan_sources(files, policy=ScanPolicy(source_roots=("src", "tools")))
    b = scan_sources(reversed(files), policy=ScanPolicy(source_roots=("tools", "src")))
    assert catalog_bytes(a) == catalog_bytes(b)
    c = scan_sources(
        files, policy=ScanPolicy(source_roots=("src", "tools"), excluded_directories=())
    )
    assert a.sources == c.sources
    assert a.scan_policy_digest != c.scan_policy_digest
    assert a.repository_digest != c.repository_digest
    assert catalog_digest(a) != catalog_digest(c)
