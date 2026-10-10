"""Shared source fixtures, without importing the illustrative experiment."""

import json
import shutil
from pathlib import Path

FIXTURE = Path(__file__).parents[1] / "fixtures/experiments/inspection"


def project(root):
    shutil.copytree(FIXTURE, root, dirs_exist_ok=True)
    return root / "train.py"


def notebook(cells):
    return json.dumps(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "code",
                    "id": f"cell-{i}",
                    "metadata": {},
                    "source": source,
                    "outputs": [],
                    "execution_count": None,
                }
                for i, source in enumerate(cells)
            ],
        }
    ).encode()


def write_source(root, source, name="train.py"):
    path = root / name
    path.write_text(source, encoding="utf-8")
    return path
