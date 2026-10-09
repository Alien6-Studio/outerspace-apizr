"""Use the installed candidate CLI to prepare and install an isolated MCP profile."""

import hashlib
import json
import os
from pathlib import Path


def prepare_profile(
    root: Path,
    cli: Path,
    preparer: Path,
    python: Path,
    house: Path,
    other_profile: Path,
) -> Path:
    from smoke_extension_packaging import snapshot
    from smoke_mcp_server import run

    output = root / "prepared"
    global_state = root / "global-plugin-state"
    global_state.mkdir()
    (global_state / "sentinel").write_text("unchanged\n")
    before = snapshot(global_state)
    other_before = snapshot(other_profile)
    env = {
        **os.environ,
        "HOME": str(global_state),
        "XDG_DATA_HOME": str(global_state),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = json.loads(
        run(
            [
                preparer,
                "plugins",
                "prepare",
                "outerspace-apizr-mcp",
                "--version",
                "0.4.4",
                "--python",
                python,
                "--platform",
                "native",
                "--wheelhouse",
                house,
                "--output-dir",
                output,
                "--json",
            ],
            root,
            env=env,
        )
    )
    assert result["state"] == "prepared", result
    assert result["installation"] == result["activation"] == "not_performed"
    assert json.loads((output / "preparation.json").read_text()) == result
    profile = output / result["profile"]
    assert not list(profile.iterdir())
    expected = []
    for artifact in result["artifacts"]:
        digest = hashlib.sha256(
            (output / "wheelhouse" / artifact["filename"]).read_bytes()
        ).hexdigest()
        assert digest == artifact["sha256"] and digest in artifact["admitted_hashes"]
        expected.append(
            f"{artifact['name']}=={artifact['version']} --hash=sha256:{digest}\n"
        )
    assert (output / "requirements.lock").read_text() == "".join(expected)
    plugin = next(
        item for item in result["artifacts"] if item["name"] == "outerspace-apizr-mcp"
    )
    run(
        [
            cli,
            "plugins",
            "install",
            output / "wheelhouse" / plugin["filename"],
            "--sha256",
            plugin["sha256"],
            "--python",
            python,
            "--requirements",
            output / "requirements.lock",
            "--wheelhouse",
            output / "wheelhouse",
            "--plugins-dir",
            profile,
        ],
        root,
        env=env,
    )
    active = json.loads(
        run(
            [cli, "plugins", "list", "--active", "--json", "--plugins-dir", profile],
            root,
            env=env,
        )
    )
    assert not active["installations"]
    assert snapshot(global_state) == before and snapshot(other_profile) == other_before
    (root / "preparation-proof.json").write_text(
        json.dumps(
            {
                "prepared": result,
                "installed": True,
                "activation_remained_explicit": True,
                "global_state_unchanged": True,
                "other_profile_unchanged": True,
                "actual_hash_equals_lock_and_is_admitted": True,
                "outside_checkout": True,
            },
            indent=2,
        )
        + "\n"
    )
    return profile
