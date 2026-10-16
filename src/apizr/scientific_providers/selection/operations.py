"""Invoke only explicitly selected trusted providers; admit all candidate evidence."""

from collections.abc import Mapping
from pathlib import Path

from pydantic import JsonValue

from apizr.contracts.json import encode
from apizr.experiments.provider_source import SourceView
from apizr.extension_runtime.errors import ExtensionError, SizeLimitExceeded
from apizr.extension_runtime.protocol import Response
from apizr.extension_runtime.supervisor import Limits
from apizr.plugins.artifacts.models import PluginError
from apizr.scientific_providers.builtin import BuiltinProvider
from apizr.scientific_providers.contracts import (
    DESCRIBE_OPERATION,
    RECOGNIZE_OPERATION,
    ProviderDescriptor,
    ProviderRequest,
    ProviderResult,
    StaticCapability,
    StaticProvider,
    admit_extension_response,
    admit_result,
    extension_arguments,
)
from apizr.scientific_providers.contracts.selection import (
    CAPABILITIES,
    CapabilityOwner,
    ProviderChoice,
    ProviderCode,
    ProviderObservation,
    ProviderReport,
    ProviderSelection,
)


class _ExtensionProvider:
    def __init__(self, choice: ProviderChoice, directory: Path | None):
        self.choice, self.directory = choice, directory

    def invoke(self, operation: str, arguments: dict[str, JsonValue]) -> Response:
        from apizr.plugins.local.activation import run_extension

        assert self.choice.extension is not None
        return run_extension(
            self.choice.extension,
            operation,
            arguments,
            directory=self.directory,
            limits=Limits(
                wall_time_ms=10000,
                max_request_bytes=4 * 1024 * 1024,
                max_stdout_bytes=1024 * 1024,
            ),
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        response = self.invoke(DESCRIBE_OPERATION, {})
        return ProviderDescriptor.model_validate_json(encode(response.result, 65536))

    def recognize(self, request: ProviderRequest) -> ProviderResult:
        return admit_extension_response(
            self.invoke(RECOGNIZE_OPERATION, extension_arguments(request)),
            request=request,
        )


class SelectionSession:
    """One explicit selection; no global registry, entrypoint loading or fallback."""

    def __init__(
        self,
        selection: ProviderSelection | None = None,
        *,
        implementations: Mapping[str, StaticProvider] | None = None,
        directory: Path | None = None,
    ):
        self.selection = ProviderSelection.model_validate(
            selection or ProviderSelection()
        )
        self._providers: dict[str, StaticProvider] = {}
        self._observations: list[ProviderObservation] = []
        claimed: set[str] = set()
        for choice in self.selection.providers:
            selected: tuple[StaticCapability, ...] = tuple(
                c for c in CAPABILITIES if c in choice.capabilities and c not in claimed
            )
            claimed.update(selected)
            descriptor = (
                BuiltinProvider().descriptor
                if choice.identity.name == "apizr.builtin"
                and choice.identity.version == "1"
                else None
            )
            code: ProviderCode | None = None
            if not choice.enabled:
                code = "provider_disabled"
            elif not selected:
                code = "provider_shadowed"
            else:
                try:
                    provider = (
                        BuiltinProvider()
                        if choice.identity.name == "apizr.builtin"
                        else _ExtensionProvider(choice, directory)
                        if choice.extension
                        else implementations.get(choice.identity.name)
                        if implementations
                        else None
                    )
                    if provider is None:
                        code = "provider_unavailable"
                    else:
                        descriptor = ProviderDescriptor.model_validate(
                            provider.descriptor
                        )
                        if descriptor.identity != choice.identity:
                            code, descriptor = "provider_incompatible", None
                        elif not set(selected) <= set(descriptor.capabilities):
                            code = "provider_unsupported"
                        else:
                            self._providers[choice.identity.name] = provider
                except (PluginError, ExtensionError):
                    code = "provider_unavailable"
                except (ValueError, TypeError):
                    code, descriptor = "provider_incompatible", None
                except Exception:
                    code = "provider_unavailable"
            self._observations.append(
                ProviderObservation(
                    choice=choice,
                    descriptor=descriptor,
                    selected_capabilities=selected,
                    diagnostic=code,
                )
            )

    def report(self) -> ProviderReport:
        return ProviderReport(
            providers=tuple(self._observations),
            available=tuple(
                p.choice.identity
                for p in self._observations
                if p.descriptor is not None
            ),
            active=tuple(p.choice.identity for p in self._observations if p.active),
            owners=tuple(
                CapabilityOwner(
                    capability=c,
                    provider=p.choice.identity if p else None,
                    state="static" if p and p.active else "unknown",
                )
                for c in CAPABILITIES
                for p in (
                    next(
                        (p for p in self._observations if c in p.selected_capabilities),
                        None,
                    ),
                )
            ),
        )

    def recognize(
        self, source: SourceView
    ) -> tuple[ProviderReport, tuple[ProviderResult, ...]]:
        results: list[ProviderResult] = []
        for index, observation in enumerate(self._observations):
            if not observation.active:
                continue
            assert observation.descriptor is not None
            code: ProviderCode | None = None
            try:
                descriptor = ProviderDescriptor.model_validate(
                    observation.descriptor.model_copy(
                        update={"capabilities": observation.selected_capabilities}
                    )
                )
                request = ProviderRequest(provider=descriptor, source=source)
            except ValueError:
                code = "provider_limit"
            else:
                try:
                    candidate = self._providers[
                        observation.choice.identity.name
                    ].recognize(request)
                except SizeLimitExceeded:
                    code = "provider_limit"
                except ExtensionError:
                    code = "provider_failed"
                except Exception:
                    code = "provider_failed"
                else:
                    try:
                        admitted = admit_result(candidate, request=request)
                        if admitted.diagnostics:
                            code = admitted.diagnostics[0].code
                        else:
                            results.append(admitted)
                    except (ValueError, TypeError, RecursionError):
                        code = "provider_result_invalid"
            if code:
                self._observations[index] = ProviderObservation.model_validate(
                    observation.model_copy(update={"diagnostic": code})
                )
        return self.report(), tuple(results)


def list_providers(
    selection: ProviderSelection | None = None,
    *,
    implementations: Mapping[str, StaticProvider] | None = None,
    directory: Path | None = None,
) -> ProviderReport:
    return SelectionSession(
        selection, implementations=implementations, directory=directory
    ).report()
