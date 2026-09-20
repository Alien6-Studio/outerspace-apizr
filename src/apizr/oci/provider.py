"""Provider boundary: launch mechanics never enter canonical policy or plan."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .model import ContainerPlan, ContainerStatus, RuntimeImage


class ProviderError(Exception):
    def __init__(self, status: ContainerStatus = "backend_unavailable") -> None:
        super().__init__(status)
        self.status: ContainerStatus = status


@dataclass(frozen=True)
class ContainerState:
    """Internal provider evidence; never part of ContainerResult or a manifest."""

    running: bool
    status: str
    oom_killed: bool
    exit_code: int

    @property
    def terminal(self) -> bool:
        return not self.running and self.status in {"exited", "dead"}


class ContainerProvider(Protocol):
    identity: str

    def probe(self, runtime: RuntimeImage) -> None: ...
    def create(
        self, name: str, plan: ContainerPlan, root: Path, environment: Mapping[str, str]
    ) -> None: ...
    def command(self, name: str) -> Sequence[str]: ...
    def final_state(
        self, name: str, *, timeout: float = 1.0
    ) -> ContainerState | None: ...
    def remove(self, name: str) -> None: ...
