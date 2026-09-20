import os

import pytest

from apizr.generators.rest.output import write_bundle


def test_exclusive_output_accepts_new_or_empty_directory(tmp_path):
    for name, existing in [("new", False), ("empty", True)]:
        root = tmp_path / name
        if existing:
            root.mkdir()
        write_bundle(root, {"app.py": b"adapter", "source/pkg/module.py": b"source"})
        assert (root / "app.py").read_bytes() == b"adapter"
        assert (root / "source/pkg/module.py").read_bytes() == b"source"
        with pytest.raises(ValueError, match="empty"):
            write_bundle(root, {"app.py": b"changed"})
        assert (root / "app.py").read_bytes() == b"adapter"


@pytest.mark.parametrize(
    "name",
    ["../outside", "/outside", "source/../../outside", "a//b", "a/./b", "a\\b", ""],
)
def test_artifact_paths_reject_traversal_and_noncanonical_names(tmp_path, name):
    root = tmp_path / "output"
    with pytest.raises(ValueError, match="canonical"):
        write_bundle(root, {name: b"no"})
    assert not root.exists()


def test_output_parent_traversal_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="parent traversal"):
        write_bundle(tmp_path / "sub" / ".." / "escape", {"app.py": b"no"})


@pytest.mark.parametrize("nested", [False, True])
def test_output_symlink_and_symlink_parent_are_rejected(tmp_path, nested):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        write_bundle(link / "sub" if nested else link, {"app.py": b"no"})
    assert list(outside.iterdir()) == []


def test_file_created_after_empty_check_is_not_overwritten(tmp_path, monkeypatch):
    original = os.open

    def raced(path, flags, *args, **kwargs):
        if path == "app.py" and flags & os.O_EXCL:
            descriptor = original(path, flags, *args, **kwargs)
            with os.fdopen(descriptor, "wb") as file:
                file.write(b"user file")
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", raced)
    with pytest.raises(FileExistsError):
        write_bundle(tmp_path / "output", {"app.py": b"generated"})
    assert (tmp_path / "output/app.py").read_bytes() == b"user file"


def test_unsupported_filesystem_capabilities_fail_before_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "supports_dir_fd", set())
    with pytest.raises(OSError, match="filesystem support"):
        write_bundle(tmp_path / "output", {"app.py": b"no"})
    assert not (tmp_path / "output").exists()
