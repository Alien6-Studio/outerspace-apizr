"""Canonical content identity and pure Run-to-Plan binding validation."""

from hashlib import sha256
from typing import Annotated

from pydantic import Field, TypeAdapter

from apizr.contracts.json import encode
from apizr.experiments.capture_model import ExperimentPlanV2, ExperimentRunV2, Plan, Run

MAX_ARTIFACT_BYTES = 4 * 1024 * 1024
_PLAN: TypeAdapter[Plan] = TypeAdapter(
    Annotated[Plan, Field(discriminator="schema_version")]
)
_RUN: TypeAdapter[Run] = TypeAdapter(
    Annotated[Run, Field(discriminator="schema_version")]
)


def plan_bytes(plan: Plan) -> bytes:
    validated = _PLAN.validate_python(plan)
    return encode(validated.model_dump(mode="json"), MAX_ARTIFACT_BYTES)


def plan_digest(plan: Plan) -> str:
    return sha256(plan_bytes(plan)).hexdigest()


def run_bytes(run: Run) -> bytes:
    validated = _RUN.validate_python(run)
    return encode(validated.model_dump(mode="json"), MAX_ARTIFACT_BYTES)


def run_digest(run: Run) -> str:
    return sha256(run_bytes(run)).hexdigest()


def read_plan(data: bytes) -> Plan:
    """Read a bounded, explicitly versioned Plan; canonicality belongs to the store."""
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError("experiment_artifact_limit")
    return _PLAN.validate_json(data)


def read_run(data: bytes) -> Run:
    """Read v1 or v2 without accepting unknown or silently widened schema ids."""
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError("experiment_artifact_limit")
    return _RUN.validate_json(data)


def validate_run_binding(run: Run, plan: Plan) -> None:
    """Validate the supplied artifacts, their exact digest and selected source."""
    plan = _PLAN.validate_python(plan)
    run = _RUN.validate_python(run)
    if run.plan_digest != plan_digest(plan):
        raise ValueError("experiment_plan_digest_mismatch")
    if isinstance(plan, ExperimentPlanV2) or isinstance(run, ExperimentRunV2):
        if not isinstance(plan, ExperimentPlanV2) or not isinstance(
            run, ExperimentRunV2
        ):
            raise ValueError("experiment_schema_binding_mismatch")
        if run.capture != plan.capture:
            raise ValueError("experiment_capture_mismatch")
    else:
        if run.subject.capability_id != plan.subject.capability_id:
            raise ValueError("experiment_capability_mismatch")
    if run.subject != plan.subject:
        raise ValueError("experiment_source_mismatch")
