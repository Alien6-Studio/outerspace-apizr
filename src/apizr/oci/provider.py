"""Provider boundary: launch mechanics never enter canonical policy or plan."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from .model import ContainerPlan, ContainerStatus, RuntimeImage


class ProviderError(Exception):
    def __init__(self, status: ContainerStatus = "backend_unavailable") -> None:
        super().__init__(status)
        self.status: ContainerStatus = status


class ContainerProvider(Protocol):
    identity: str

    def probe(self, runtime: RuntimeImage) -> None: ...
    def create(
        self, name: str, plan: ContainerPlan, root: Path, environment: Mapping[str, str]
    ) -> None: ...
    def command(self, name: str) -> Sequence[str]: ...
    def oom_killed(self, name: str) -> bool: ...
    def remove(self, name: str) -> None: ...
