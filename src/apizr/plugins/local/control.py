"""One cooperative installation deadline, including store waits and uv children."""

import time
from dataclasses import dataclass
from threading import Event

from .models import PluginError


class InstallationCancelled(PluginError):
    def __init__(self) -> None:
        super().__init__("sync_cancelled")


class InstallationTimeout(PluginError):
    def __init__(self) -> None:
        super().__init__("sync_timeout")


@dataclass(frozen=True)
class InstallControl:
    deadline: float
    cancel: Event | None = None

    def check(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise InstallationCancelled()
        if time.monotonic() >= self.deadline:
            raise InstallationTimeout()

    def remaining(self) -> float:
        self.check()
        return max(0, self.deadline - time.monotonic())
