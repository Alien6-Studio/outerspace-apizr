"""Explicit provider authority, refusals and immutable history without producers."""

import json

import pytest
from pydantic import ValidationError

from apizr.experiments.comparison import ChangeState, compare_stored_runs
from apizr.experiments.history import show_run, show_text
from apizr.experiments.inspection import inspect_experiment
from apizr.experiments.inspection_model import SectionState
from apizr.experiments.reporting import inspection_bytes, text_report
from apizr.experiments.runner import run_experiment
from apizr.scientific_providers.builtin import BuiltinProvider
from apizr.scientific_providers.contracts import (
    ProducerIdentity,
    ProviderDescriptor,
    ProviderLimits,
)
from apizr.scientific_providers.contracts.selection import (
    ProviderChoice,
    ProviderSelection,
    read_provenance,
)
from apizr.scientific_providers.selection import SelectionSession, list_providers
from apizr.workspace.provider_selection import load_selection

SOURCE = (
    "from sklearn.metrics import accuracy_score\nscore = accuracy_score([1], [1])\n"
)


class Alternative:
    def __init__(self, mode="ok"):
        self.mode, self.calls = mode, 0

    @property
    def descriptor(self):
        return ProviderDescriptor(
            identity=ProducerIdentity(
                name="example.alternative",
                version="2" if self.mode == "version" else "1",
            ),
            capabilities=("metric_signals",),
            limits=ProviderLimits(max_source_bytes=1)
            if self.mode == "limit"
            else ProviderLimits(),
        )

    def recognize(self, request):
        self.calls += 1
        if self.mode == "raise":
            raise RuntimeError("private-source-secret")
        result = BuiltinProvider().recognize(
            request.model_copy(
                update={
                    "provider": BuiltinProvider().descriptor.model_copy(
                        update={"capabilities": ("metric_signals",)}
                    )
                }
            )
        )
        result = result.model_copy(update={"identity": self.descriptor.identity})
        return (
            result.model_copy(update={"source_digest": "a" * 64})
            if self.mode == "invalid"
            else result
        )


def selection(*, enabled=True, builtin=False):
    choices = (
        ProviderChoice(
            identity=ProducerIdentity(name="example.alternative", version="1"),
            capabilities=("metric_signals",),
            enabled=enabled,
        ),
    )
    return ProviderSelection(
        providers=choices + (ProviderSelection().providers if builtin else ())
    )


def test_inventory_reports_actual_versions_capabilities_and_limits():
    default = list_providers()
    assert (
        default.active == default.available == (BuiltinProvider().descriptor.identity,)
    )
    assert default.providers[0].descriptor == BuiltinProvider().descriptor
    off = list_providers(
        ProviderSelection(
            providers=(ProviderChoice(identity=default.active[0], enabled=False),)
        )
    )
    assert not off.active and off.available == default.available
    assert all(o.state == "unknown" for o in off.owners)


@pytest.mark.parametrize(
    "mode,enabled,code",
    [
        ("missing", True, "provider_unavailable"),
        ("version", True, "provider_incompatible"),
        ("raise", True, "provider_failed"),
        ("invalid", True, "provider_result_invalid"),
        ("limit", True, "provider_limit"),
        ("ok", False, "provider_disabled"),
    ],
)
def test_refusal_is_unknown_no_exception_or_fallback(tmp_path, mode, enabled, code):
    path = tmp_path / "model.py"
    path.write_text(SOURCE)
    implementation = Alternative(mode)
    result = inspect_experiment(
        path,
        providers=selection(enabled=enabled, builtin=True),
        provider_implementations={}
        if mode == "missing"
        else {"example.alternative": implementation},
    )
    assert result.providers.providers[0].diagnostic == code
    assert result.providers.owners[1].state == "unknown"
    assert (
        result.metrics.signals == () and result.states.metrics == SectionState.UNKNOWN
    )
    assert "private-source-secret" not in inspection_bytes(
        result
    ).decode() + text_report(result)
    assert code in text_report(result)
    if mode in ("missing", "version", "limit") or not enabled:
        assert implementation.calls == 0


def test_first_owner_wins_while_other_capabilities_keep_the_builtin(tmp_path):
    path = tmp_path / "model.py"
    path.write_text(SOURCE)
    alternate = Alternative()
    result = inspect_experiment(
        path,
        providers=selection(builtin=True),
        provider_implementations={"example.alternative": alternate},
    )
    assert len(result.metrics.signals) == 1 and alternate.calls == 1
    assert result.providers.owners[1].provider.name == "example.alternative"
    assert "metric_signals" not in result.providers.providers[1].selected_capabilities
    assert result.providers.providers[1].active


def test_disabled_and_shadowed_code_is_never_accessed():
    class Bomb:
        @property
        def descriptor(self):
            raise AssertionError("Not selected")

    config = ProviderSelection(
        providers=ProviderSelection().providers + selection().providers
    )
    report = list_providers(config, implementations={"example.alternative": Bomb()})
    assert report.providers[1].diagnostic == "provider_shadowed"


def test_recorded_provenance_survives_removing_all_implementations(
    tmp_path, monkeypatch
):
    path = tmp_path / "model.py"
    path.write_text("score = 0.75\n")
    first = run_experiment(
        path, providers=ProviderSelection(providers=()), store=tmp_path / "history"
    )
    second = run_experiment(path, store=tmp_path / "history")
    report = read_provenance(second.plan.execution.controls)
    assert report.active == (BuiltinProvider().descriptor.identity,)

    def unavailable(*args, **kwargs):
        raise AssertionError("History must not load or invoke providers")

    monkeypatch.setattr(BuiltinProvider, "recognize", unavailable)
    monkeypatch.setattr(SelectionSession, "__init__", unavailable)
    stored = show_run(tmp_path / "history", second.run_digest)
    assert "apizr.builtin 1" in show_text(stored)
    diff = compare_stored_runs(
        tmp_path / "history", first.run_digest, second.run_digest
    )
    assert diff.providers.state == ChangeState.CHANGED
    assert not diff.providers.a.active and diff.providers.b.active


@pytest.mark.parametrize(
    "raw",
    [
        '{"schema_version":"apizr.provider-selection/v1","providers":[],"providers":[]}',
        "[" * 30 + "]" * 30,
        '{"providers":[],' + '"x":"' + "a" * 65536 + '"}',
    ],
)
def test_explicit_configuration_is_bounded_and_unambiguous(tmp_path, raw):
    path = tmp_path / "providers.json"
    path.write_text(raw)
    with pytest.raises(ValueError):
        load_selection(path)


def test_portable_report_rejects_a_forged_owner_or_active_inventory():
    report = list_providers()
    with pytest.raises(ValidationError):
        type(report).model_validate(report.model_copy(update={"active": ()}))
    owners = report.owners
    forged = owners[0].model_copy(update={"provider": None})
    with pytest.raises(ValidationError):
        type(report).model_validate(
            report.model_copy(update={"owners": (forged, *owners[1:])})
        )
    with pytest.raises(ValidationError):
        ProviderSelection(providers=ProviderSelection().providers * 2)


@pytest.mark.parametrize(
    "change",
    [
        {"capabilities": ("metric_signals", "metric_signals")},
        {"extension": "external"},
    ],
)
def test_reserved_builtin_and_duplicate_capabilities(change):
    choice = ProviderSelection().providers[0]
    with pytest.raises(ValueError):
        ProviderChoice.model_validate(choice.model_copy(update=change))


@pytest.mark.parametrize(
    "change",
    [
        {"selected_capabilities": ("input_reads", "input_reads")},
        {"descriptor": Alternative().descriptor},
        {"descriptor": None},
        {
            "choice": ProviderSelection()
            .providers[0]
            .model_copy(update={"enabled": False}),
            "diagnostic": "provider_failed",
        },
    ],
)
def test_inconsistent_observations_are_rejected(change):
    observed = list_providers().providers[0]
    with pytest.raises(ValueError):
        type(observed).model_validate(observed.model_copy(update=change))


def test_retained_provider_identity_cannot_change():
    observed = list_providers(
        selection(), implementations={"example.alternative": Alternative()}
    ).providers[0]
    descriptor = observed.descriptor.model_copy(
        update={"identity": ProducerIdentity(name="example.alternative", version="2")}
    )
    with pytest.raises(ValueError, match="provider_identity_mismatch"):
        type(observed).model_validate(
            observed.model_copy(update={"descriptor": descriptor})
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("owners", ()),
        ("owners", tuple(reversed(list_providers().owners))),
        (
            "providers",
            (
                list_providers()
                .providers[0]
                .model_copy(update={"selected_capabilities": ("metric_signals",)}),
            ),
        ),
    ],
)
def test_inconsistent_report_precedence_is_rejected(field, value):
    report = list_providers()
    with pytest.raises(ValueError):
        type(report).model_validate(report.model_copy(update={field: value}))


@pytest.mark.parametrize(
    "mode,code",
    [
        ("invalid_descriptor", "provider_incompatible"),
        ("missing_descriptor", "provider_unavailable"),
        ("unsupported", "provider_unsupported"),
        ("extension_error", "provider_unavailable"),
    ],
)
def test_descriptor_failures_are_explicit(mode, code):
    from apizr.extension_runtime.errors import PluginFailed

    class Refused:
        @property
        def descriptor(self):
            if mode == "invalid_descriptor":
                raise ValueError("private")
            if mode == "missing_descriptor":
                raise RuntimeError("private")
            if mode == "extension_error":
                raise PluginFailed()
            return Alternative().descriptor.model_copy(
                update={"capabilities": ("input_reads",)}
            )

    report = list_providers(
        selection(), implementations={"example.alternative": Refused()}
    )
    assert report.providers[0].diagnostic == code


@pytest.mark.parametrize(
    "mode,code",
    [
        ("size", "provider_limit"),
        ("extension", "provider_failed"),
        ("diagnostic", "provider_unsupported"),
    ],
)
def test_recognition_refusal_vocabulary(mode, code):
    from apizr.experiments.provider_source import SourceView
    from apizr.extension_runtime.errors import PluginFailed, SizeLimitExceeded
    from apizr.scientific_providers.contracts import (
        ProviderDiagnostic,
        ProviderLocation,
    )

    class Refused(Alternative):
        def recognize(self, request):
            if mode == "size":
                raise SizeLimitExceeded("stdout")
            if mode == "extension":
                raise PluginFailed()
            return (
                super()
                .recognize(request)
                .model_copy(
                    update={
                        "diagnostics": (
                            ProviderDiagnostic(
                                code=code,
                                location=ProviderLocation(
                                    source=request.source.reference
                                ),
                            ),
                        )
                    }
                )
            )

    report, results = SelectionSession(
        selection(), implementations={"example.alternative": Refused()}
    ).recognize(SourceView(reference="s.py", text=SOURCE))
    assert not results and report.providers[0].diagnostic == code


def test_extension_protocol_admission_and_missing_installation(monkeypatch, tmp_path):
    import apizr.plugins.local.activation as activation
    from apizr.experiments.provider_source import SourceView
    from apizr.extension_runtime.protocol import Response
    from apizr.scientific_providers.contracts import ProviderRequest

    choice = selection().providers[0].model_copy(update={"extension": "alternate"})
    config = ProviderSelection(providers=(choice,))
    missing = list_providers(config, directory=tmp_path / "absent")
    assert missing.providers[0].diagnostic == "provider_unavailable"
    calls = []

    def invoke(name, operation, arguments, **kwargs):
        calls.append((name, operation, kwargs))
        result = (
            Alternative().descriptor
            if operation == "scientific.describe"
            else Alternative().recognize(
                ProviderRequest.model_validate_json(json.dumps(arguments))
            )
        )
        return Response(
            request_id="a" * 32,
            operation=operation,
            protocol="apizr.extension/v1",
            status="ok",
            result=result.model_dump(mode="json"),
        )

    monkeypatch.setattr(activation, "run_extension", invoke)
    report, results = SelectionSession(config, directory=tmp_path).recognize(
        SourceView(reference="s.py", text=SOURCE)
    )
    assert report.active == (choice.identity,) and len(results) == 1
    assert [c[1] for c in calls] == ["scientific.describe", "scientific.recognize"]
    assert calls[0][2]["limits"].wall_time_ms == 10000


@pytest.mark.parametrize("capability", ["input_reads", "randomness_controls"])
def test_external_occurrences_do_not_receive_builtin_locations(tmp_path, capability):
    class Other(Alternative):
        @property
        def descriptor(self):
            return super().descriptor.model_copy(update={"capabilities": (capability,)})

        def recognize(self, request):
            return (
                BuiltinProvider()
                .recognize(
                    request.model_copy(
                        update={
                            "provider": BuiltinProvider().descriptor.model_copy(
                                update={"capabilities": (capability,)}
                            )
                        }
                    )
                )
                .model_copy(update={"identity": self.descriptor.identity})
            )

    choice = selection().providers[0].model_copy(update={"capabilities": (capability,)})
    path = tmp_path / "s.py"
    path.write_text(
        'import pandas as pd\nimport random\nx=pd.read_csv("data.csv")\nrandom.seed(7)\n'
    )
    result = inspect_experiment(
        path,
        providers=ProviderSelection(providers=(choice, *ProviderSelection().providers)),
        provider_implementations={"example.alternative": Other()},
    )
    prefix = (
        "/data/artifacts/" if capability == "input_reads" else "/randomness/controls/"
    )
    assert not any(
        location.evidence.startswith(prefix) for location in result.locations
    )


def test_explicit_builtin_limit_retains_diagnostics_without_locations(tmp_path):
    path = tmp_path / "s.py"
    path.write_text("import random\n" + "random.seed(None)\n" * 513)
    result = inspect_experiment(path, providers=ProviderSelection())
    assert result.randomness.diagnostics[0].code == "randomness_discovery_limit"


def test_provider_diff_text_and_historical_controls(tmp_path):
    from apizr.experiments.comparison_reporting import diff_text
    from apizr.experiments.model import EvidenceOrigin, Parameter

    path = tmp_path / "s.py"
    path.write_text("x=1\n")
    first = run_experiment(
        path, providers=ProviderSelection(providers=()), store=tmp_path / "history"
    )
    second = run_experiment(path, store=tmp_path / "history")
    assert "Scientific provider provenance" in diff_text(
        compare_stored_runs(tmp_path / "history", first.run_digest, second.run_digest)
    )
    assert (
        read_provenance(
            (
                Parameter(
                    name="scientific_providers", origin=EvidenceOrigin.STATIC, value=42
                ),
            )
        )
        is None
    )
    assert (
        read_provenance(
            (
                Parameter(
                    name="scientific_providers",
                    origin=EvidenceOrigin.STATIC,
                    value={"schema_version": "future"},
                ),
            )
        )
        is None
    )
