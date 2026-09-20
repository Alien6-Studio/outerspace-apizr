"""Docker Engine launcher for the OCI-container contract; never pulls images."""

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, Field

from .model import ContainerPlan, RuntimeImage
from .provider import ProviderError


class HostInfo(BaseModel):
    OSType: str
    MemoryLimit: bool
    SwapLimit: bool
    CpuCfsQuota: bool
    CpuCfsPeriod: bool
    PidsLimit: bool
    SecurityOptions: list[str]


class ImageConfig(BaseModel):
    Volumes: dict[str, object] | None = None
    Labels: dict[str, str] = Field(default_factory=dict)


class ImageInfo(BaseModel):
    Id: str
    Os: str
    Architecture: str
    Config: ImageConfig


class ContainerState(BaseModel):
    OOMKilled: bool


class DockerProvider:
    identity = "apizr.docker-engine/v1"

    def run(
        self, arguments: Sequence[str], *, environment: Mapping[str, str] | None = None
    ) -> bytes:
        try:
            result = subprocess.run(
                ["docker", *arguments],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=environment,
                timeout=10,
                check=True,
            )
            return result.stdout
        except (OSError, subprocess.SubprocessError) as error:
            raise ProviderError() from error

    def probe(self, runtime: RuntimeImage) -> None:
        if os.name != "posix":
            raise ProviderError()
        try:
            info = HostInfo.model_validate_json(
                self.run(["info", "--format", "{{json .}}"])
            )
            if (
                info.OSType != "linux"
                or not all(
                    (
                        info.MemoryLimit,
                        info.SwapLimit,
                        info.CpuCfsQuota,
                        info.CpuCfsPeriod,
                        info.PidsLimit,
                    )
                )
                or not any(
                    value == "name=seccomp,profile=builtin"
                    for value in info.SecurityOptions
                )
            ):
                raise ProviderError()
        except ValueError as error:
            raise ProviderError() from error
        try:
            image = ImageInfo.model_validate_json(
                self.run(["image", "inspect", "--format", "{{json .}}", runtime.image])
            )
            if (
                image.Id != runtime.image
                or image.Os + "/" + image.Architecture != runtime.platform
            ):
                raise ValueError("image_identity")
            if (
                image.Config.Volumes
                or image.Config.Labels.get("org.apizr.worker.protocol")
                != "apizr.runtime/v1"
            ):
                raise ValueError("image_contract")
        except (ValueError, ProviderError) as error:
            raise ProviderError("runtime_image_unavailable") from error

    def create(
        self, name: str, plan: ContainerPlan, root: Path, environment: Mapping[str, str]
    ) -> None:
        if any(character in str(root) for character in (",", "\n", "\r")):
            raise ProviderError()
        resources = plan.policy.resources
        arguments = [
            "create",
            "--pull=never",
            "--name",
            name,
            "--label",
            "org.apizr.execution=oci-v1",
            "--platform",
            plan.runtime.platform,
            "--interactive",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges=true",
            "--user=65532:65532",
            "--network=none",
            "--ipc=private",
            "--cgroupns=private",
            "--restart=no",
            "--no-healthcheck",
            "--log-driver=none",
            "--memory",
            str(resources.memory_bytes),
            "--memory-swap",
            str(resources.memory_bytes),
            "--cpu-period=100000",
            "--cpu-quota",
            str(resources.cpu_millis * 100),
            "--pids-limit",
            str(resources.pids),
            "--shm-size=65536",
            "--tmpfs",
            f"/tmp:rw,nosuid,nodev,noexec,size={resources.scratch_bytes},mode=1777",
            "--mount",
            f"type=bind,src={root},dst=/bundle,readonly,bind-propagation=rprivate",
            "--workdir=/bundle",
            "--entrypoint=/usr/local/bin/python",
        ]
        for key in sorted(environment):
            arguments.extend(["--env", key])
        arguments.extend(
            [
                plan.runtime.image,
                "-I",
                "-B",
                "-m",
                "apizr.oci.entrypoint",
                *sorted(environment),
            ]
        )
        # Docker reads values from its process environment, never command arguments.
        self.run(arguments, environment={**os.environ, **environment})

    def command(self, name: str) -> Sequence[str]:
        return ["docker", "start", "--attach", "--interactive", name]

    def oom_killed(self, name: str) -> bool:
        try:
            return ContainerState.model_validate_json(
                self.run(["inspect", "--format", "{{json .State}}", name])
            ).OOMKilled
        except (ProviderError, ValueError):
            # Absence of reliable evidence must never be reported as an OOM.
            return False

    def remove(self, name: str) -> None:
        # rm -f terminates the container namespace, including setsid descendants.
        # Named before create so partial/failed creation can also be cleaned up.
        for _ in range(3):
            try:
                self.run(["rm", "--force", "--volumes", name])
                return
            except ProviderError:
                try:
                    remaining = self.run(
                        ["ps", "--all", "--quiet", "--filter", f"name=^/{name}$"]
                    )
                    if not remaining.strip():
                        return
                except ProviderError:
                    pass
        raise ProviderError("cleanup_failed")
