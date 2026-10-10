"""Bounded factual presentation of an ExperimentDiff; no evidence capture."""

import json
from collections.abc import Iterable

from apizr.experiments.comparison import (
    ChangeState,
    DifferenceCounts,
    EnvironmentChange,
    ExperimentDiff,
    diff_bytes,
)
from apizr.experiments.model import ExperimentValue

MAX_TEXT_BYTES = 256 * 1024
MAX_SECTION_ITEMS = 200
MAX_VALUE_CHARS = 384
DISCLAIMER = (
    "These are recorded evidence differences. Apizr does not establish which "
    "difference caused an observed result change.\n"
)
TRUNCATED = "[Display limited; full evidence is available in --format json.]\n"


def _value(value: ExperimentValue | None) -> str:
    if value is None:
        return "not recorded"
    raw = json.dumps(value.model_dump(mode="json"), sort_keys=True, ensure_ascii=True)
    return raw if len(raw) <= MAX_VALUE_CHARS else raw[:MAX_VALUE_CHARS] + "…"


def _pair(
    label: str, state: ChangeState, a: ExperimentValue | None, b: ExperimentValue | None
) -> str:
    return f"  {label} — {state.value.upper()}\n    A {_value(a)}\n    B {_value(b)}\n"


def _counts(value: DifferenceCounts) -> str:
    return f"{value.changed} changed, {value.added} added, {value.removed} removed, {value.unknown} unknown"


def _limit(items: Iterable[str]) -> Iterable[str]:
    for index, item in enumerate(items):
        if index >= MAX_SECTION_ITEMS:
            yield TRUNCATED
            break
        yield item


def _environment(label: str, value: EnvironmentChange) -> Iterable[str]:
    yield f"  {label}\n"
    for name in ("python_implementation", "python_version", "platform", "architecture"):
        item = getattr(value, name)
        yield _pair(name, item.state, item.a, item.b)
    yield from _limit(
        _pair(f"package {item.name} evidence", item.state, item.a, item.b)
        for item in value.packages
    )
    yield from _limit(
        _pair(f"artifact {item.name} evidence", item.state, item.a, item.b)
        for item in value.artifacts
    )


def _sections(value: ExperimentDiff) -> Iterable[str]:
    yield f"Material evidence differences ({_counts(value.material_counts)})\n"
    if not (
        value.material_counts.changed
        + value.material_counts.added
        + value.material_counts.removed
    ):
        yield "No material recorded differences among comparable evidence.\n"
    yield f"Code — {value.source.state.value.upper()}\n"
    for name in (
        "kind",
        "reference",
        "digest",
        "executable_digest",
        "module",
        "capability_id",
    ):
        state = getattr(value.source, name)
        a, b = getattr(value.source.a, name), getattr(value.source.b, name)
        yield f"  {name}: A {a if a is not None else 'unknown'}; B {b if b is not None else 'unknown'} — {state.value.upper()}\n"
    yield "Data\n"
    yield from _limit(
        _pair(
            f"{item.name} planned selection",
            item.selection_state,
            item.planned_a,
            item.planned_b,
        )
        + _pair(
            f"{item.name} observed content",
            item.content_state,
            item.observed_a,
            item.observed_b,
        )
        + f"    planned reference: {item.reference_state.value.upper()}\n"
        for item in value.data
    )
    yield "Parameters\n"
    yield from _limit(
        _pair(
            f"{item.name} intended", item.planned_state, item.planned_a, item.planned_b
        )
        + _pair(
            f"{item.name} observed",
            item.observed_state,
            item.observed_a,
            item.observed_b,
        )
        + f"    observed evidence membership: {item.observed_membership.value.upper()}\n"
        for item in value.parameters
    )
    yield "Randomness\n"
    yield from _limit(
        _pair(
            f"{item.provider}.{item.name} intended",
            item.planned_state,
            item.planned_a,
            item.planned_b,
        )
        + _pair(
            f"{item.provider}.{item.name} observed",
            item.observed_state,
            item.observed_a,
            item.observed_b,
        )
        for item in value.randomness
    )
    yield "Environment\n"
    yield from _environment("Plan evidence", value.planned_environment)
    yield from _environment("Run evidence", value.observed_environment)
    yield f"Serving — {value.serving.value.upper()}\n"
    yield f"Observed result differences ({_counts(value.result_counts)})\n"
    yield f"Status: A {value.status.a}; B {value.status.b} — {value.status.state.value.upper()}\n"
    yield "Metrics\n"
    yield from _limit(
        _pair(f"{item.name} evidence", item.state, item.a, item.b)
        + (f"    delta B - A: {item.delta:+g}\n" if item.delta is not None else "")
        for item in value.metrics
    )
    yield "Outputs\n"
    yield from _limit(
        _pair(f"{item.name} evidence", item.state, item.a, item.b)
        + f"    content: {item.content_state.value.upper()}\n"
        for item in value.outputs
    )


def diff_text(value: ExperimentDiff) -> str:
    """Full input IDs and disclaimer survive all presentation limits."""
    diff_bytes(value)
    result = (
        "Experiment diff — A → B\n"
        f"Run A: {value.run_a_digest}\nRun B: {value.run_b_digest}\n"
        f"Plan A: {value.plan_a_digest}\nPlan B: {value.plan_b_digest}\n"
        f"Plan identity: {value.plan_state.value.upper()}\n"
        "Counts describe comparison facets; planned and observed evidence are counted separately.\n"
        "Timing is excluded. Added/removed describe recorded evidence membership.\n\n"
    )
    size = len(result.encode("utf-8"))
    reserve = len((TRUNCATED + DISCLAIMER).encode("utf-8"))
    parts = [result]
    for part in _sections(value):
        size += len(part.encode("utf-8"))
        if size + reserve > MAX_TEXT_BYTES:
            parts.append(TRUNCATED)
            break
        parts.append(part)
    parts.append(DISCLAIMER)
    return "".join(parts)
