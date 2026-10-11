"""Real offline preparation binds selected wheel bytes and isolates installation."""

import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from apizr.cli import main
from apizr.plugins.artifacts.requirements import parse_lock
from apizr.plugins.local import (
    enable_extension,
    install_extension,
    list_extensions,
    run_extension,
)
from apizr.plugins.preparation.operations import prepare_plugin

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def preparation_inputs(chain):
    plugin, digest, lock, house = chain
    shutil.copyfile(plugin, house / plugin.name)
    return plugin, digest, lock, house


def prepare(inputs, output, **options):
    _, _, lock, house = inputs
    return prepare_plugin(
        "local-probe",
        "1.0",
        python=Path(sys.executable),
        platform="native",
        output_dir=output,
        wheelhouse=house,
        requirements=lock,
        **options,
    )


def test_prepare_then_install_then_explicit_activation_isolates_profiles(
    preparation_inputs, tmp_path, monkeypatch
):
    global_state = tmp_path / "global"
    global_state.mkdir()
    sentinel = global_state / "must-stay"
    sentinel.write_text("unchanged")
    monkeypatch.setenv("HOME", str(global_state))
    monkeypatch.setenv("XDG_DATA_HOME", str(global_state))
    monkeypatch.setenv("UV_INDEX_URL", "http://127.0.0.1:1/must-not-connect")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    output, other = tmp_path / "prepared", tmp_path / "other-profile"
    result = prepare(preparation_inputs, output)
    assert result.state == "prepared", result
    assert result.installation == result.activation == "not_performed"
    assert not list((output / "profile").iterdir())
    assert not list_extensions(directory=other).installations
    raw = (output / "requirements.lock").read_bytes()
    parsed = parse_lock(raw)
    assert len(parsed.packages) == 3
    for item in result.artifacts:
        actual = hashlib.sha256(
            (output / "wheelhouse" / item.filename).read_bytes()
        ).hexdigest()
        assert actual == item.sha256 and actual in item.admitted_hashes
        assert (
            next(pin for pin in parsed.packages if pin.name == item.name).sha256
            == actual
        )
    plugin = next(item for item in result.artifacts if item.name == "local-probe")
    install_extension(
        output / "wheelhouse" / plugin.filename,
        plugin.sha256,
        directory=output / "profile",
        python=Path(sys.executable),
        requirements=output / "requirements.lock",
        wheelhouse=output / "wheelhouse",
    )
    assert not list_extensions(directory=output / "profile", active=True).installations
    enable_extension("local-probe", "1.0", directory=output / "profile")
    assert (
        run_extension(
            "local-probe", "describe", {}, directory=output / "profile"
        ).result
        == 42
    )
    assert not list_extensions(directory=other, active=True).installations
    assert {path.name: path.read_text() for path in global_state.iterdir()} == {
        "must-stay": "unchanged"
    }


def test_multi_hash_selects_actual_wheel_not_first_hash(
    preparation_inputs, wheel_factory, tmp_path
):
    _, _, lock, house = preparation_inputs
    foreign, foreign_hash = wheel_factory(
        name="locked-leaf",
        plugin=False,
        filename="locked_leaf-1.0-cp312-cp312-win_amd64.whl",
        files={
            "locked_leaf-1.0.dist-info/WHEEL": b"Wheel-Version: 1.0\nTag: cp312-cp312-win_amd64\n"
        },
    )
    shutil.copyfile(foreign, house / foreign.name)
    actual = hashlib.sha256(
        next(house.glob("locked_leaf-*-py3-none-any.whl")).read_bytes()
    ).hexdigest()
    lock.write_text(
        lock.read_text().replace(
            f"locked-leaf==1.0 --hash=sha256:{actual}",
            f"locked-leaf==1.0 \\\n  --hash=sha256:{foreign_hash} \\\n  --hash=sha256:{actual}",
        )
    )
    result = prepare(preparation_inputs, tmp_path / "prepared")
    assert result.state == "prepared", result
    leaf = next(item for item in result.artifacts if item.name == "locked-leaf")
    assert leaf.sha256 == actual != foreign_hash
    assert leaf.admitted_hashes == tuple(sorted((actual, foreign_hash)))
    assert foreign_hash not in (tmp_path / "prepared/requirements.lock").read_text()
    assert not (tmp_path / "prepared/wheelhouse" / foreign.name).exists()


@pytest.mark.parametrize(
    "case,reason",
    [
        ("wrong_hash", "wheel_hash_not_admitted"),
        ("missing_wheel", "compatible_wheel_unavailable"),
        ("ambiguous", "wheel_selection_ambiguous"),
        ("wrong_platform", "compatible_wheel_unavailable"),
        ("metadata_tags", "invalid_wheel_tags"),
    ],
)
def test_refusal_never_publishes_partial_output(
    preparation_inputs, wheel_factory, tmp_path, case, reason
):
    _, _, lock, house = preparation_inputs
    leaf = next(house.glob("locked_leaf*"))
    digest = hashlib.sha256(leaf.read_bytes()).hexdigest()
    if case == "wrong_hash":
        lock.write_text(lock.read_text().replace(digest, "0" * 64))
    elif case == "missing_wheel":
        leaf.unlink()
    else:
        filename = (
            "locked_leaf-1.0-1-py3-none-any.whl"
            if case == "ambiguous"
            else "locked_leaf-1.0-cp312-cp312-win_amd64.whl"
        )
        tags = (
            b"Wheel-Version: 1.0\nTag: py3-none-any\n"
            if case != "wrong_platform"
            else b"Wheel-Version: 1.0\nTag: cp312-cp312-win_amd64\n"
        )
        if case == "metadata_tags":
            filename = "locked_leaf-1.0-py3-none-any.whl"
            tags = b"Wheel-Version: 1.0\nTag: cp312-cp312-win_amd64\n"
        replacement, replacement_hash = wheel_factory(
            name="locked-leaf",
            plugin=False,
            filename=filename,
            files={"locked_leaf-1.0.dist-info/WHEEL": tags},
        )
        if case != "ambiguous":
            leaf.unlink()
        shutil.copyfile(replacement, house / replacement.name)
        lock.write_text(lock.read_text().replace(digest, replacement_hash))
    output = tmp_path / "prepared"
    result = prepare(preparation_inputs, output)
    assert result.state == "refused" and result.diagnostics[0].reason == reason, result
    assert not output.exists()
    assert not list(tmp_path.glob(".apizr-preparation-*"))
    assert str(tmp_path) not in result.model_dump_json()


def test_offline_resolution_and_cli(preparation_inputs, tmp_path, capsys):
    _, _, _, house = preparation_inputs
    output = tmp_path / "prepared"
    assert (
        main(
            [
                "plugins",
                "prepare",
                "local-probe",
                "--version",
                "1.0",
                "--python",
                sys.executable,
                "--platform",
                "native",
                "--wheelhouse",
                str(house),
                "--output-dir",
                str(output),
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "prepared" and result["profile"] == "profile"
    assert json.loads((output / "preparation.json").read_bytes()) == result


def test_normalized_outputs_ignore_location_and_input_order(
    preparation_inputs, tmp_path
):
    _, _, lock, _ = preparation_inputs
    first = tmp_path / "first"
    assert prepare(preparation_inputs, first).state == "prepared"
    lock.write_text("\n".join(reversed(lock.read_text().splitlines())) + "\n")
    second = tmp_path / "second"
    assert prepare(preparation_inputs, second).state == "prepared"
    for name in ("requirements.lock", "preparation.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_hash_seeds_produce_identical_preparation_evidence(
    preparation_inputs, tmp_path
):
    import os
    import subprocess

    program = """import sys
from pathlib import Path
from apizr.plugins.preparation.operations import prepare_plugin
result = prepare_plugin('local-probe','1.0',python=Path(sys.executable),platform='native',output_dir=Path(sys.argv[1]),wheelhouse=Path(sys.argv[2]),requirements=Path(sys.argv[3]))
assert result.state == 'prepared', result
"""
    _, _, lock, house = preparation_inputs
    outputs = []
    for seed in ("1", "739"):
        output = tmp_path / ("seed-" + seed)
        subprocess.run(
            [sys.executable, "-c", program, str(output), str(house), str(lock)],
            env={**os.environ, "PYTHONHASHSEED": seed},
            check=True,
            capture_output=True,
            timeout=15,
        )
        outputs.append(
            (
                (output / "requirements.lock").read_bytes(),
                (output / "preparation.json").read_bytes(),
            )
        )
    assert outputs[0] == outputs[1]


def test_preparation_result_schema_matches_documented_contract(
    preparation_inputs, tmp_path
):
    import jsonschema

    from apizr.plugins.preparation.models import PreparationResult

    schema = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "docs/specs/apizr-plugin-preparation-v1.schema.json"
        ).read_text()
    )
    assert schema == PreparationResult.model_json_schema()
    result = prepare(preparation_inputs, tmp_path / "prepared")
    jsonschema.validate(result.model_dump(mode="json", by_alias=True), schema)
