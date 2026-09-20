"""Static REST/OpenAPI v1 consumer of Capability IR and Readiness."""

from .generator import generate, render
from .model import Manifest, RestPlan
from .planner import plan

__all__ = ["generate", "render", "plan", "Manifest", "RestPlan"]
