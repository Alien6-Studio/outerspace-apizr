"""Static MCP Tools compiler; importing it does not import the MCP SDK."""

from .generator import generate, render
from .planner import plan

__all__ = ["generate", "render", "plan"]
