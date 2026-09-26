"""Build real, dependency-free wheels without running any build backend."""

import base64
import csv
import hashlib
import io
import json
import zipfile

import pytest


@pytest.fixture
def wheel_factory(tmp_path):
    def build(
        *,
        name="local-probe",
        version="1.0",
        manifest_changes=None,
        metadata_extra="",
        files=None,
        manifest_raw=None,
        filename=None,
        plugin=True,
    ):
        normalized = name.replace("-", "_")
        info = f"{normalized}-{version}.dist-info"
        manifest = {
            "schema": "apizr.extension-manifest/v1",
            "name": name,
            "version": version,
            "module": "local_probe",
            "protocol": "apizr.extension/v1",
        }
        manifest.update(manifest_changes or {})
        content = {
            "local_probe.py": b"import json,sys\nr=json.load(sys.stdin)\nprint(json.dumps({k:r[k] for k in ('protocol','request_id','operation')}|{'status':'ok','result':'installed'}))\n",
            "apizr-extension.json": manifest_raw
            if manifest_raw is not None
            else json.dumps(manifest).encode(),
            f"{info}/METADATA": f"Metadata-Version: 2.3\nName: {name}\nVersion: {version}\n{metadata_extra}\n".encode(),
            f"{info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: apizr-tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        }
        if not plugin:
            del content["apizr-extension.json"]
            del content["local_probe.py"]
        content.update(files or {})
        record = io.StringIO()
        writer = csv.writer(record, lineterminator="\n")
        for path, data in content.items():
            writer.writerow(
                (
                    path,
                    "sha256="
                    + base64.urlsafe_b64encode(hashlib.sha256(data).digest())
                    .rstrip(b"=")
                    .decode(),
                    len(data),
                )
            )
        writer.writerow((info + "/RECORD", "", ""))
        content[info + "/RECORD"] = record.getvalue().encode()
        wheel = tmp_path / (filename or f"{normalized}-{version}-py3-none-any.whl")
        with zipfile.ZipFile(wheel, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path, data in content.items():
                archive.writestr(path, data)
        return wheel, hashlib.sha256(wheel.read_bytes()).hexdigest()

    return build


@pytest.fixture
def chain(wheel_factory, tmp_path):
    leaf, leaf_hash = wheel_factory(
        name="locked-leaf", plugin=False, files={"locked_leaf.py": b"VALUE = 41\n"}
    )
    helper, helper_hash = wheel_factory(
        name="locked-helper",
        plugin=False,
        metadata_extra="Requires-Dist: locked-leaf==1.0\n",
        files={"locked_helper.py": b"from locked_leaf import VALUE\nVALUE += 1\n"},
    )
    plugin, digest = wheel_factory(
        metadata_extra="Requires-Dist: locked-helper==1.0\n",
        files={
            "local_probe.py": b"import json,sys\nfrom locked_helper import VALUE\nr=json.load(sys.stdin)\nprint(json.dumps({k:r[k] for k in ('protocol','request_id','operation')}|{'status':'ok','result':VALUE}))\n"
        },
    )
    wheelhouse = tmp_path / "wheels"
    wheelhouse.mkdir()
    leaf = leaf.rename(wheelhouse / leaf.name)
    helper = helper.rename(wheelhouse / helper.name)
    lock = tmp_path / "requirements.lock"
    lock.write_text(
        f"local-probe==1.0 --hash=sha256:{digest}\nlocked-helper==1.0 --hash=sha256:{helper_hash}\nlocked-leaf==1.0 --hash=sha256:{leaf_hash}\n"
    )
    return plugin, digest, lock, wheelhouse
