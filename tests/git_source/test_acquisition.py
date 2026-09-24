from pathlib import Path
from threading import Event

import pytest

from apizr.compiler import assess_readiness, prepare_exposure, render_bundle
from apizr.exposure import ExposurePolicy
from apizr.git_source import AcquisitionLimits, GitSourceError, acquire_snapshot
from apizr.repository_readiness import RepositoryReadinessPolicy

from .conftest import git_fixture

pytestmark = pytest.mark.timeout(25)


@pytest.mark.parametrize(
    "ref", ["main", "v1", "annotated", "refs/heads/main", "refs/tags/v1", "commit"]
)
def test_real_snapshot_and_cleanup(remote, tls, scratch, ref):
    url, source, commit = remote
    reference = commit if ref == "commit" else ref
    with acquire_snapshot(url, reference, subdir="service", ca_file=tls[0]) as snapshot:
        assert snapshot.commit == commit
        assert snapshot.repository == url and snapshot.requested_ref == reference
        assert snapshot.subdir == "service"
        assert (
            snapshot.root.joinpath("calculator.py").read_bytes()
            == source.joinpath("service/calculator.py").read_bytes()
        )
        assert not list(snapshot.root.parent.rglob(".git"))
    assert not snapshot.root.exists()


def test_retained_sources_and_moving_branch(remote, tls, scratch):
    url, source, commit = remote
    policy = ExposurePolicy.model_validate(
        {
            "interfaces": ["rest", "mcp"],
            "execution": {"allowed": ["direct"]},
            "selection": {"include_all_ready": True},
        }
    )
    readiness = RepositoryReadinessPolicy.model_validate(
        {"execution": {"modes": ["direct"]}}
    )
    local = prepare_exposure(
        source / "service", policy=policy, readiness_policy=readiness
    )
    with acquire_snapshot(url, "main", subdir="service", ca_file=tls[0]) as snapshot:
        (source / "service/calculator.py").write_text(
            "raise RuntimeError('must not run')\n"
        )
        git_fixture.git(source, "commit", "-am", "move branch")
        assert git_fixture.git(source, "rev-parse", "HEAD") != snapshot.commit == commit
        prepared = prepare_exposure(
            snapshot.root, policy=policy, readiness_policy=readiness
        )
        assert prepared.plan == local.plan
        assert (
            assess_readiness(snapshot.root, readiness_policy=readiness)
            == local.readiness
        )
    assert not snapshot.root.exists()
    for interface in ("rest", "mcp"):
        bundle = render_bundle(prepared, interface=interface)
        assert bundle == render_bundle(local, interface=interface)
        assert all(".git" not in Path(name).parts for name in bundle)


@pytest.mark.parametrize(
    "ref,code", [("absent", "git_ref_not_found"), ("ambiguous", "git_ambiguous_ref")]
)
def test_missing_and_ambiguous(remote, tls, scratch, ref, code):
    url, source, _ = remote
    git_fixture.git(source, "branch", "ambiguous")
    git_fixture.git(source, "tag", "ambiguous")
    with pytest.raises(GitSourceError, match=code):
        with acquire_snapshot(url, ref, ca_file=tls[0]):
            pytest.fail("accepted")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/a",
        "ssh://example.com/a",
        "https://user:secret@example.com/a",
        "--upload-pack=bad",
        "https://example.com/a?secret=1",
        "https://example.com:bad/a",
        "https://example.com/%0a",
        "https://example.com/a#fragment",
    ],
)
def test_invalid_url_before_git(url, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *a: pytest.fail("Git lookup"))
    with pytest.raises(GitSourceError, match="git_invalid_url"):
        with acquire_snapshot(url, "main"):
            pytest.fail("accepted")


@pytest.mark.parametrize(
    "ref",
    [
        "",
        "--upload-pack=x",
        "main~1",
        "main:foo",
        "@{1}",
        "../a",
        "refs/remotes/x",
        "a\nb",
        "/a",
        "a.lock",
    ],
)
def test_invalid_ref_before_git(ref, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *a: pytest.fail("Git lookup"))
    with pytest.raises(GitSourceError, match="git_invalid_ref"):
        with acquire_snapshot("https://example.com/a", ref):
            pytest.fail("accepted")


@pytest.mark.parametrize(
    "subdir", ["../outside", "/tmp", "a/../../x", ".git", "a\\..\\b", "a//b"]
)
def test_path_escape(remote, tls, scratch, subdir):
    with pytest.raises(GitSourceError, match="git_invalid_path"):
        with acquire_snapshot(remote[0], "main", subdir=subdir, ca_file=tls[0]):
            pytest.fail("accepted")


def test_absent_git(remote, monkeypatch, scratch):
    monkeypatch.setattr("shutil.which", lambda *a: None)
    with pytest.raises(GitSourceError, match="git_not_found"):
        with acquire_snapshot(remote[0], "main"):
            pytest.fail("accepted")


@pytest.mark.parametrize("kind", ["tls", "network", "subdir", "cancel"])
def test_failed_acquisitions_clean_and_next_works(remote, tls, scratch, kind):
    cancel = Event()
    if kind == "cancel":
        cancel.set()
    with pytest.raises(GitSourceError):
        with acquire_snapshot(
            remote[0] + ("/missing" if kind == "network" else ""),
            "main",
            subdir="absent" if kind == "subdir" else ".",
            ca_file=None if kind == "tls" else tls[0],
            cancel=cancel,
        ):
            pytest.fail("accepted")
    assert not list(scratch.iterdir())
    with acquire_snapshot(remote[0], "main", ca_file=tls[0]):
        pass


@pytest.mark.parametrize(
    "limits,code",
    [
        (AcquisitionLimits(max_file_bytes=1), "git_snapshot_limit"),
        (AcquisitionLimits(max_snapshot_bytes=1), "git_snapshot_limit"),
        (AcquisitionLimits(max_acquisition_bytes=1), "git_acquisition_limit"),
        (AcquisitionLimits(max_stdout_bytes=1), "git_output_limit"),
    ],
)
def test_limits(remote, tls, scratch, limits, code):
    with pytest.raises(GitSourceError, match=code):
        with acquire_snapshot(remote[0], "main", ca_file=tls[0], limits=limits):
            pytest.fail("accepted")


@pytest.mark.parametrize(
    "kind,code",
    [
        ("symlink", "git_symlinks_unsupported"),
        ("submodule", "git_submodules_unsupported"),
        ("lfs", "git_lfs_unsupported"),
    ],
)
def test_incomplete_or_unsafe_sources_refused(remote, tls, scratch, kind, code):
    url, source, commit = remote
    if kind == "submodule":
        git_fixture.git(
            source, "update-index", "--add", "--cacheinfo", f"160000,{commit},nested"
        )
    else:
        if kind == "symlink":
            (source / "external.py").symlink_to("/etc/passwd")
        else:
            (source / "data").write_text(
                "version https://git-lfs.github.com/spec/v1\noid sha256:"
                + "a" * 64
                + "\nsize 10\n"
            )
        git_fixture.git(source, "add", ".")
    git_fixture.git(source, "commit", "-m", kind)
    with pytest.raises(GitSourceError, match=code):
        with acquire_snapshot(url, "main", ca_file=tls[0]):
            pytest.fail("accepted")


def test_no_config_hooks_filters_or_project_execution(
    remote, tls, scratch, tmp_path, monkeypatch
):
    url, source, _ = remote
    marker = tmp_path / "executed"
    attack = f"touch {marker}"
    (source / "danger.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
    )
    (source / ".gitattributes").write_text(
        "*.py filter=evil\nservice/calculator.py export-ignore\n"
    )
    git_fixture.git(source, "add", ".")
    git_fixture.git(source, "commit", "-m", "hostile attributes and module")
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    for name in ("post-checkout", "post-merge", "reference-transaction"):
        hook = hooks / name
        hook.write_text(f"#!/bin/sh\n{attack}\n")
        hook.chmod(0o700)
    config = tmp_path / "evil.gitconfig"
    config.write_text(
        f'[core]\n hooksPath = {hooks}\n[filter "evil"]\n smudge = {attack}\n required = true\n[credential]\n helper = !{attack}\n[url "ext::{attack}"]\n insteadOf = https://\n'
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(config))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(hooks))
    monkeypatch.setenv("GIT_ASKPASS", str(hooks / "post-checkout"))
    monkeypatch.setenv("GIT_SSL_NO_VERIFY", "true")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    with acquire_snapshot(url, "main", ca_file=tls[0]) as snapshot:
        assert (snapshot.root / "service/calculator.py").is_file()
        assess_readiness(snapshot.root)
    assert not marker.exists()
    # An inherited "insecure" flag must not make the same certificate trusted.
    with pytest.raises(GitSourceError, match="git_command_failed"):
        with acquire_snapshot(url, "main"):
            pytest.fail("inherited TLS override")


def test_caller_errors_and_interruptions_not_reclassified(remote, tls, scratch):
    for exception in (ValueError("compiler error"), KeyboardInterrupt()):
        with pytest.raises(type(exception)) as caught:
            with acquire_snapshot(remote[0], "main", ca_file=tls[0]):
                raise exception
        assert caught.value is exception


def test_temp_directory_inside_hostile_checkout_does_not_inherit_local_config(
    remote, tls, tmp_path, monkeypatch
):
    import tempfile

    url, source, _ = remote
    nested = source / "temporary"
    nested.mkdir()
    git_fixture.git(source, "config", "url.https://127.0.0.1:1/blocked.insteadOf", url)
    monkeypatch.setattr(tempfile, "tempdir", str(nested))
    with acquire_snapshot(url, "main", ca_file=tls[0]) as snapshot:
        assert (snapshot.root / "service/calculator.py").is_file()
    assert not list(nested.iterdir())
