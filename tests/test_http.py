import io
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient

from apizr.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_upload_returns_self_contained_project(client):
    response = client.post(
        "/process_file/",
        files={
            "file": (
                "uploaded.py",
                "def add(a: int, b: int = 1):\n    return a + b\n",
                "text/plain",
            )
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert {
            "uploaded.py",
            "uploaded_api.py",
            "Dockerfile",
            "requirements.txt",
            "start.sh",
        } <= set(archive.namelist())


@pytest.mark.parametrize(
    "name",
    ["../escape.py", "/tmp/escape.py", "..\\escape.py", "wrong.txt"],
)
def test_unsafe_upload_names_rejected(client, name):
    result = client.post("/process_file/", files={"file": (name, "def hello(): pass")})
    assert result.status_code == 400


def test_invalid_code_is_client_error(client):
    result = client.post(
        "/process_file/", files={"file": ("invalid.py", "def broken(")}
    )
    assert result.status_code == 400


def test_oversized_upload(client):
    result = client.post(
        "/process_file/", files={"file": ("big.py", b"x" * (10 * 1024 * 1024 + 1))}
    )
    assert result.status_code == 413


def test_analysis_filter_and_removed_filesystem_endpoint(client):
    result = client.post(
        "/code/analyze_file/?functions_to_analyze=chosen",
        files={"file": ("code.py", "def chosen(): pass\ndef ignored(): pass")},
    )
    assert result.status_code == 200
    assert [f["name"] for f in result.json()["functions"]] == ["chosen"]
    assert (
        client.post(
            "/code/analyse_directory/", params={"directory_path": "/tmp"}
        ).status_code
        == 404
    )


def test_docker_endpoint_does_not_write_requested_directory(client, tmp_path):
    target = tmp_path / "must_not_exist"
    result = client.post(
        "/docker/generate_dockerfile/",
        json={
            "conf": {"project_path": str(target)},
            "requirements": "fastapi\nuvicorn\n",
        },
    )
    assert result.status_code == 200, result.text
    assert "Dockerfile" in result.json()
    assert not target.exists()


def test_windows_upload_name_validation():
    from fastapi import HTTPException, UploadFile

    from apizr.http import read_upload

    with pytest.raises(HTTPException) as error:
        read_upload(UploadFile(filename="C:\\escape.py", file=io.BytesIO(b"")), {".py"})
    assert error.value.status_code == 400


@pytest.mark.parametrize(
    "content",
    [
        "not JSON",
        "{}",
        '{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}',
    ],
)
def test_invalid_or_empty_notebooks_are_client_errors(client, content):
    response = client.post("/process_file/", files={"file": ("invalid.ipynb", content)})
    assert response.status_code == 400
