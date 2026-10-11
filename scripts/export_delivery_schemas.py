"""Regenerate schemas for the existing public delivery result models."""

import json
from pathlib import Path

from apizr.contracts.results import (
    AdmissionResult,
    BuildResult,
    DeliveryResult,
    ObservationResult,
    PublishResult,
    PushResult,
)

MODELS = (
    BuildResult,
    PushResult,
    DeliveryResult,
    PublishResult,
    AdmissionResult,
    ObservationResult,
)


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "docs/specs"
    for model in MODELS:
        schema = model.model_json_schema()
        name = (
            schema["properties"]["schema"]["default"]
            .replace(".", "-", 1)
            .replace("/", "-")
        )
        (root / (name + ".schema.json")).write_text(
            json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
        )


if __name__ == "__main__":
    main()
