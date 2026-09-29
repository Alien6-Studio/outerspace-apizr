"""Managed multi-destination delivery and explicit resume of an existing build."""

from .models import (
    BatchRequest,
    BatchResult,
    Destination,
    DestinationOutcome,
    ProofInputs,
)
from .operations import BatchError, deliver_batch

__all__ = [
    "BatchRequest",
    "BatchResult",
    "Destination",
    "DestinationOutcome",
    "ProofInputs",
    "BatchError",
    "deliver_batch",
]
