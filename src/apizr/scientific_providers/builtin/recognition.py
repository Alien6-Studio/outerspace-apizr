"""One privately owned tree for built-in rules; export only immutable evidence."""

from dataclasses import dataclass

from pydantic import TypeAdapter

from apizr.experiments.inputs import InputResult
from apizr.experiments.metrics import MetricDiscoveryResult
from apizr.experiments.model import Reference
from apizr.experiments.outputs import OutputDiscoveryResult
from apizr.experiments.provider_source import SourceLimit, bounded_tree
from apizr.experiments.randomness import RandomnessDiagnostic, RandomnessResult

from . import inputs, metrics, outputs, randomness
from .locations import InputLocations, RandomnessLocations


@dataclass(frozen=True, slots=True)
class Recognition:
    input_reads: InputResult
    metric_signals: MetricDiscoveryResult
    output_candidates: OutputDiscoveryResult
    randomness_controls: RandomnessResult
    inputs: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = ()
    controls: tuple[tuple[tuple[str, str], tuple[tuple[int, int], ...]], ...] = ()


def recognize_source(source: str | bytes, reference: str) -> Recognition:
    """Keep individual producer diagnostics and bounds, including legacy bytes."""
    try:
        TypeAdapter[str](Reference).validate_python(reference, strict=True)
        tree = bounded_tree(source)
    except (
        SourceLimit,
        ValueError,
        UnicodeError,
        SyntaxError,
        RecursionError,
        TypeError,
    ):
        return Recognition(
            inputs.discover_inputs(source, source_reference=reference),
            metrics.discover_metrics(source, source_reference=reference),
            outputs.discover_outputs(source, source_reference=reference),
            randomness.discover_randomness(source, source_reference=reference),
        )
    input_visitor = InputLocations(reference)
    metric_visitor = metrics.Discovery(reference)
    output_visitor = outputs.Discovery(reference)
    random_visitor = RandomnessLocations(reference)
    for visitor in (input_visitor, metric_visitor, output_visitor):
        visitor.visit(tree)
    locations = True
    try:
        random_visitor.visit(tree)
        random_result = randomness.discovery_result(random_visitor, tree)
    except SourceLimit:
        # Historical location tracing also stops entirely on this producer limit.
        locations = False
        random_result = RandomnessResult(
            diagnostics=(
                RandomnessDiagnostic(
                    code="randomness_discovery_limit", source=reference
                ),
            )
        )
    return Recognition(
        inputs.discovery_result(input_visitor),
        metrics.discovery_result(metric_visitor),
        outputs.discovery_result(output_visitor),
        random_result,
        tuple(
            (key, tuple(sorted(value)))
            for key, value in input_visitor.locations.items()
        )
        if locations
        else (),
        tuple(
            (key, tuple(sorted(value)))
            for key, value in random_visitor.locations.items()
        )
        if locations
        else (),
    )
