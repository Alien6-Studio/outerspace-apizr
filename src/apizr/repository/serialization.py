"""Independent policy, repository and catalog content identities."""

import json
from typing import TYPE_CHECKING

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel

if TYPE_CHECKING:
    from .model import Catalog
    from .policy import ScanPolicy


def canonical_bytes(model: ValueModel) -> bytes:
    return (
        json.dumps(
            model.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def policy_bytes(policy: "ScanPolicy") -> bytes:
    return canonical_bytes(policy)


def policy_digest(policy: "ScanPolicy") -> Digest:
    return Digest.of_bytes(policy_bytes(policy))


def catalog_bytes(catalog: "Catalog") -> bytes:
    # Revalidate models supplied by callers, including model_copy/model_construct.
    from .model import Catalog

    validated = Catalog.model_validate(catalog.model_dump(mode="json"))
    return canonical_bytes(validated)


def catalog_digest(catalog: "Catalog") -> Digest:
    return Digest.of_bytes(catalog_bytes(catalog))
