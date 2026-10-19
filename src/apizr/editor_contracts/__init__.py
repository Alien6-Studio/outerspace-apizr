"""Versioned contracts for editor integrations."""

from .discovery import capabilities
from .model import EditorDiagnostic, EditorRequest, EditorResponse, EngineCapabilities

__all__ = [
    "capabilities",
    "EditorDiagnostic",
    "EditorRequest",
    "EditorResponse",
    "EngineCapabilities",
]
