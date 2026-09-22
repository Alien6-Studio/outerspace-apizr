"""Repository entrypoint adapter over the unchanged reviewed Docker launcher."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from apizr.oci.docker import DockerProvider, ImageInfo
from apizr.oci.model import ContainerPlan, RuntimeImage
from apizr.oci.provider import ProviderError

from .model import RepositoryContainerPlan


class RepositoryDockerProvider(DockerProvider):
    def probe(self, runtime: RuntimeImage) -> None:
        super().probe(
            runtime
        )  # Preserve host controls, exact ID/platform and old marker.
        try:
            image = ImageInfo.model_validate_json(
                self.run(["image", "inspect", "--format", "{{json .}}", runtime.image])
            )
            if (
                image.Id != runtime.image
                or image.Os + "/" + image.Architecture != runtime.platform
                or image.Config.Labels.get("org.apizr.repository.worker.protocol")
                != "apizr.repository-runtime/v1"
            ):
                raise ValueError("repository_worker_contract")
        except (ValueError, ProviderError) as error:
            raise ProviderError("runtime_image_unavailable") from error

    def create_repository(
        self,
        name: str,
        plan: RepositoryContainerPlan,
        root: Path,
        environment: Mapping[str, str],
    ) -> None:
        # The reviewed launch method consumes only policy.resources and runtime.
        # This structural adapter constructs no single-source plan/Inspection.
        super().create(name, cast(ContainerPlan, plan), root, environment)

    def run(
        self,
        arguments: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        timeout: float = 10,
    ) -> bytes:
        selected = list(arguments)
        if selected and selected[0] == "create":
            index = selected.index("apizr.oci.entrypoint")
            selected[index] = "apizr.repository_execution.entrypoint"
        return super().run(selected, environment=environment, timeout=timeout)
