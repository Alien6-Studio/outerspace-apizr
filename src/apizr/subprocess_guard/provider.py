"""Require the strict worker protocol and preserve the existing Docker controls."""

from collections.abc import Mapping, Sequence

from apizr.oci.docker import DockerProvider, ImageInfo
from apizr.oci.model import RuntimeImage
from apizr.oci.provider import ProviderError

PROTOCOL = "apizr.subprocess-deny/v1"
LABEL = "org.apizr.subprocess-deny.protocol"


class DenyDockerProvider(DockerProvider):
    entrypoint = "apizr.subprocess_guard.entrypoint"

    def probe(self, runtime: RuntimeImage) -> None:
        super().probe(runtime)
        try:
            image = ImageInfo.model_validate_json(
                self.run(["image", "inspect", "--format", "{{json .}}", runtime.image])
            )
            if image.Id != runtime.image or image.Config.Labels.get(LABEL) != PROTOCOL:
                raise ValueError("subprocess_deny_worker_contract")
        except (ValueError, ProviderError) as error:
            raise ProviderError("runtime_image_unavailable") from error

    def run(
        self,
        arguments: Sequence[str],
        *,
        environment: Mapping[str, str] | None = None,
        timeout: float = 10,
    ) -> bytes:
        selected = list(arguments)
        if selected and selected[0] == "create":
            selected[selected.index("apizr.oci.entrypoint")] = self.entrypoint
        # The repository adapter uses this same reviewed create method. Its
        # alternate run() must not replace the strict entrypoint again.
        return DockerProvider.run(
            self, selected, environment=environment, timeout=timeout
        )
