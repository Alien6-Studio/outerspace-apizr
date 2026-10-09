"""Canonical content identity and pure Run-to-Plan binding validation."""

from hashlib import sha256

from apizr.contracts.json import encode
from apizr.experiments.model import ExperimentPlan, ExperimentRun

MAX_ARTIFACT_BYTES = 4 * 1024 * 1024


def plan_bytes(plan: ExperimentPlan) -> bytes:
    validated = ExperimentPlan.model_validate(plan)
    return encode(validated.model_dump(mode="json"), MAX_ARTIFACT_BYTES)


def plan_digest(plan: ExperimentPlan) -> str:
    return sha256(plan_bytes(plan)).hexdigest()


def run_bytes(run: ExperimentRun) -> bytes:
    validated = ExperimentRun.model_validate(run)
    return encode(validated.model_dump(mode="json"), MAX_ARTIFACT_BYTES)


def run_digest(run: ExperimentRun) -> str:
    return sha256(run_bytes(run)).hexdigest()


def validate_run_binding(run: ExperimentRun, plan: ExperimentPlan) -> None:
    """Validate the supplied artifacts, their exact digest and selected source."""
    plan = ExperimentPlan.model_validate(plan)
    run = ExperimentRun.model_validate(run)
    if run.plan_digest != plan_digest(plan):
        raise ValueError("experiment_plan_digest_mismatch")
    if run.subject.capability_id != plan.subject.capability_id:
        raise ValueError("experiment_capability_mismatch")
    if run.subject != plan.subject:
        raise ValueError("experiment_source_mismatch")
