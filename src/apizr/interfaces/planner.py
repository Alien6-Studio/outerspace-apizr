"""Validate bound artifacts and consume eligibility; never analyze user source."""

from collections.abc import Mapping, Sequence

from apizr.capabilities.model import Capability, Digest, Source
from apizr.capabilities.types import ValueModel
from apizr.inspection import Inspection
from apizr.readiness.model import Assessment

from .model import Input, InvocationContract, TypeSpec
from .schema import lower


class BoundSource(ValueModel):
    source: Source
    executable_digest: Digest
    executable_path: str
    ir_digest: Digest
    readiness_digest: Digest


class InterfacePlan(BoundSource):
    capabilities: tuple[InvocationContract, ...]


class GenerationRefused(ValueError):
    """Selected declarations lack readiness eligibility; nothing may be emitted."""


def invocation_contract(
    capability: Capability,
    assessment: Assessment,
    structured: Mapping[str, TypeSpec] | None = None,
) -> InvocationContract:
    """Lower validated signature evidence after the caller enforces eligibility.

    Single-source and repository planners own their distinct eligibility checks.
    This primitive neither grants eligibility nor analyzes project source.
    """
    if (
        capability.id != assessment.capability_id
        or capability.source != assessment.source
        or not assessment.in_ir
    ):
        raise ValueError("Invocation evidence disagrees with the capability")
    if capability.execution not in ("sync", "async"):
        raise ValueError("Inconsistent eligible IR execution form")
    # Unknown outputs remain documentation; return annotations are not enforced.
    returns = (
        TypeSpec(kind="any")
        if assessment.dimensions.outputs.reasons
        else lower(capability.signature.returns.annotation, structured)
    )
    return InvocationContract(
        capability_id=capability.id,
        name=capability.name,
        execution="async" if capability.execution == "async" else "sync",
        parameters=tuple(
            Input(
                name=p.name,
                kind=p.kind,
                required=p.required,
                type=lower(p.annotation, structured),
            )
            for p in capability.signature.parameters
        ),
        returns=returns,
        description=capability.docstring,
    )


def plan(
    inspection: Inspection,
    source: bytes,
    *,
    executable: bytes | None = None,
    select: Sequence[str] | None = None,
) -> InterfacePlan:
    # Revalidate even objects made with model_construct/model_copy bypasses.
    inspected = Inspection.model_validate(inspection.model_dump(mode="json"))
    ir = inspected.capability_ir
    readiness = inspected.readiness
    if Digest.of_bytes(source) != ir.source.digest:
        raise ValueError("Source bytes do not match the inspected source digest")
    if ir.source.kind == "python":
        if executable is not None and executable != source:
            raise ValueError("Python executable must be the exact inspected source")
        executable = source
    if executable is None or Digest.of_bytes(executable) != (
        ir.source.transformed_digest or ir.source.digest
    ):
        raise ValueError("Executable bytes do not match the inspected Python digest")
    capabilities = {c.id: c for c in ir.capabilities}
    assessments = {a.capability_id: a for a in readiness.assessments}
    declarations = set(capabilities) | {
        f"python:{d.source.module}:{d.source.symbol}" for d in ir.diagnostics
    }
    if declarations != set(assessments):
        raise ValueError("Readiness identities do not cover the IR declarations")
    for identity, assessment in assessments.items():
        capability = capabilities.get(identity)
        if assessment.in_ir != (capability is not None):
            raise ValueError("Readiness IR membership does not match the document")
        if capability and (
            assessment.source != capability.source
            or assessment.effects != capability.effects
        ):
            raise ValueError("Readiness capability evidence does not match the IR")
    if not assessments:
        raise ValueError("No callable declarations to generate")
    by_name = {a.source.symbol: a.capability_id for a in assessments.values()}
    if select is None:
        chosen = set(assessments)
    else:
        if not select:
            raise ValueError("Selection cannot be empty")
        chosen: set[str] = set()
        for name in select:
            identity = by_name.get(name, name)
            if identity not in assessments:
                raise ValueError(f"Unknown capability selection: {name}")
            chosen.add(identity)
    rejected = [
        assessments[i]
        for i in sorted(chosen)
        if not assessments[i].can_generate_interface
    ]
    if rejected:
        details: list[str] = []
        for assessment in rejected:
            codes = sorted(
                {
                    r.code.value
                    for dimension in (
                        assessment.dimensions.binding,
                        assessment.dimensions.execution,
                        assessment.dimensions.inputs,
                        assessment.dimensions.outputs,
                    )
                    for r in dimension.reasons
                }
            )
            details.append(
                f"{assessment.source.symbol}: {assessment.state.value} ({', '.join(codes)})"
            )
        raise GenerationRefused(
            "Generation refused; select only eligible capabilities: "
            + "; ".join(details)
        )
    endpoints = tuple(
        invocation_contract(
            capabilities[identity],
            assessments[identity],
            {
                declaration.name: declaration.type
                for declaration in readiness.structured_types
                if declaration.type is not None
            },
        )
        for identity in sorted(chosen)
    )
    return InterfacePlan(
        source=ir.source,
        executable_digest=Digest.of_bytes(executable),
        executable_path="source/" + "/".join(ir.source.module.split(".")) + ".py",
        ir_digest=inspected.ir_digest,
        readiness_digest=inspected.readiness_digest,
        capabilities=endpoints,
    )
