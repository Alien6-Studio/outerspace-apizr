"""Single-source inspection envelope. Presentation is distinct from canonical IR."""

import json
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from apizr.capabilities import CapabilityDocument, document_digest
from apizr.capabilities import inspect_source as inspect_capabilities
from apizr.capabilities.model import Digest, Severity
from apizr.capabilities.types import ValueModel
from apizr.readiness import ReadinessReport, State, assess, report_digest


class Inspection(ValueModel):
    schema_version: Literal["apizr.inspection/v1"] = "apizr.inspection/v1"
    capability_ir: CapabilityDocument
    ir_digest: Digest
    readiness: ReadinessReport
    readiness_digest: Digest

    @model_validator(mode="after")
    def consistent_digests(self) -> Self:
        if (
            self.ir_digest != document_digest(self.capability_ir)
            or self.readiness.ir_digest != self.ir_digest
            or self.readiness_digest != report_digest(self.readiness)
            or self.readiness.source != self.capability_ir.source
        ):
            raise ValueError("Inspection artifacts and digests must agree")
        return self

    @property
    def exit_code(self) -> int:
        return int(
            any(
                a.state in {State.AMBIGUOUS, State.UNSUPPORTED}
                for a in self.readiness.assessments
            )
            or any(d.severity == Severity.ERROR for d in self.capability_ir.diagnostics)
        )


def _assemble(document: CapabilityDocument, source: str | bytes) -> Inspection:
    readiness = assess(document, source)
    return Inspection(
        capability_ir=document,
        ir_digest=document_digest(document),
        readiness=readiness,
        readiness_digest=report_digest(readiness),
    )


def inspect_source(source: str | bytes, *, module_name: str) -> Inspection:
    return _assemble(inspect_capabilities(source, module_name=module_name), source)


def inspect_file(path: str | Path, *, module_name: str) -> Inspection:
    path = Path(path)
    if path.suffix not in {".py", ".ipynb"}:
        raise ValueError("Inspection supports one .py or .ipynb file")
    raw = path.read_bytes()
    if path.suffix == ".py":
        return inspect_source(raw, module_name=module_name)
    # Keep notebook/exporter dependencies outside the Python-only core path.
    from apizr.capability_notebooks import inspect_notebook_bytes

    notebook = inspect_notebook_bytes(raw, module_name=module_name)
    return _assemble(notebook.document, notebook.python_source)


def json_bytes(inspection: Inspection) -> bytes:
    return (
        json.dumps(
            inspection.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def text_report(inspection: Inspection) -> str:
    ir = inspection.capability_ir
    capabilities = {c.id: c for c in ir.capabilities}
    lines = [
        "Apizr inspection",
        f"Source: {ir.source.module} ({ir.source.kind})",
        f"Source digest: sha256:{ir.source.digest.value}",
        f"IR digest: sha256:{inspection.ir_digest.value}",
        f"Readiness policy: {inspection.readiness.policy_version}",
        f"Capabilities: {len(ir.capabilities)}",
        f"Assessments: {len(inspection.readiness.assessments)}",
        "",
    ]
    for assessment in inspection.readiness.assessments:
        capability = capabilities.get(assessment.capability_id)
        lines.extend(
            [
                assessment.source.symbol,
                f"  readiness: {assessment.state.value.upper()}",
                f"  can generate interface: {str(assessment.can_generate_interface).lower()}",
            ]
        )
        if capability:
            annotation = capability.signature.returns.annotation
            lines.extend(
                [
                    f"  execution: {capability.execution.value}",
                    f"  input contract: {assessment.dimensions.inputs.state.value}",
                    f"  return declaration: {annotation.declared if annotation else 'unknown'} (enforcement: none)",
                ]
            )
        lines.append("  effects: unknown (not an execution approval)")
        for dimension in (
            assessment.dimensions.binding,
            assessment.dimensions.execution,
            assessment.dimensions.inputs,
            assessment.dimensions.outputs,
        ):
            for reason in dimension.reasons:
                parameter = f" [{reason.parameter}]" if reason.parameter else ""
                lines.append(
                    f"  {reason.code.value} line {reason.line}{parameter}: {reason.message}"
                )
        lines.append("")
    lines.append(f"IR diagnostics: {len(ir.diagnostics)}")
    lines.extend(
        f"  {d.code.value} {d.severity.value} {d.source.symbol}: {d.message}"
        for d in ir.diagnostics
    )
    return "\n".join(lines) + "\n"
