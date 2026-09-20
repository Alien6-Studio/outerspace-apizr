import os
from pathlib import Path

import pytest

from apizr.oci.docker import DockerProvider
from apizr.oci.model import RuntimeImage


@pytest.fixture(scope="session")
def worker_image():
    path = os.environ.get("APIZR_TEST_OCI_IMAGE")
    if not path:
        pytest.skip(
            "Explicit worker image required; CI isolation job always provides one"
        )
    image = RuntimeImage.model_validate_json(Path(path).read_bytes())
    DockerProvider().probe(
        image
    )  # Configured integration must fail, never silently skip.
    return image
