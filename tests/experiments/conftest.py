"""Explicit fictional fraud-detection evidence, never a captured execution."""

from datetime import UTC, datetime
from hashlib import sha256

import pytest

from apizr.experiments import (
    EnvironmentEvidence,
    EnvironmentValue,
    EvidenceOrigin,
    ExecutionIntent,
    ExperimentPlan,
    ExperimentRun,
    InputArtifact,
    Metric,
    OutputArtifact,
    PackageEvidence,
    Parameter,
    RandomnessControl,
    RunTiming,
    SourceIdentity,
    plan_digest,
)


def digest(label):
    return sha256(label.encode()).hexdigest()


def example_pair():
    declared, static, runtime, unknown = (
        EvidenceOrigin.DECLARED,
        EvidenceOrigin.STATIC,
        EvidenceOrigin.RUNTIME,
        EvidenceOrigin.UNKNOWN,
    )
    subject = SourceIdentity(
        kind="notebook",
        reference="notebooks/fraud_detection.ipynb",
        digest=digest("fictional notebook source"),
        executable_digest=digest("fictional transformed notebook"),
        module="fraud_detection",
        capability_id=None,
    )
    plan = ExperimentPlan(
        subject=subject,
        inputs=(
            InputArtifact(
                name="train",
                reference="data/train.csv",
                digest=digest("fictional training data"),
                size=4096,
                origin=static,
            ),
            InputArtifact(
                name="validation", reference="data/validation.csv", origin=unknown
            ),
        ),
        parameters=(
            Parameter(name="max_depth", value=8, origin=declared),
            Parameter(name="learning_rate", value=0.05, origin=declared),
        ),
        randomness=(
            RandomnessControl(
                provider="sklearn", name="random_state", value=42, origin=declared
            ),
        ),
        environment=EnvironmentEvidence(
            python_implementation=EnvironmentValue(value="CPython", origin=declared),
            python_version=EnvironmentValue(value="3.12.13", origin=declared),
            platform=EnvironmentValue(value=None, origin=unknown),
            packages=(
                PackageEvidence(name="scikit-learn", version="1.7.2", origin=declared),
            ),
            artifacts=(
                InputArtifact(
                    name="lock",
                    reference="requirements.lock",
                    digest=digest("fictional intended lock"),
                    origin=static,
                ),
            ),
        ),
        execution=ExecutionIntent(
            kind="trusted-notebook",
            policy_digest=digest("fictional execution policy"),
            controls=(Parameter(name="network", value=False, origin=declared),),
        ),
    )
    run = ExperimentRun(
        plan_digest=plan_digest(plan),
        subject=subject,
        status="success",
        observed_inputs=(
            InputArtifact(
                name="train",
                reference="data/train.csv",
                digest=digest("fictional training data"),
                size=4096,
                origin=runtime,
            ),
        ),
        effective_parameters=(
            Parameter(name="max_depth", value=8, origin=runtime),
            Parameter(name="learning_rate", value=0.05, origin=runtime),
        ),
        randomness=(
            RandomnessControl(
                provider="sklearn", name="random_state", value=42, origin=runtime
            ),
        ),
        environment=EnvironmentEvidence(
            python_implementation=EnvironmentValue(value="CPython", origin=runtime),
            python_version=EnvironmentValue(value="3.12.13", origin=runtime),
            platform=EnvironmentValue(value="linux-x86_64", origin=runtime),
            packages=(
                PackageEvidence(name="scikit-learn", version="1.7.2", origin=runtime),
            ),
            artifacts=(
                InputArtifact(
                    name="lock",
                    reference="requirements.lock",
                    digest=digest("fictional intended lock"),
                    origin=runtime,
                ),
            ),
        ),
        metrics=(Metric(name="roc_auc", value=0.91, origin=runtime),),
        outputs=(
            OutputArtifact(
                name="fraud-model",
                digest=digest("fictional trained model"),
                size=1024,
                media_type="application/octet-stream",
                origin=runtime,
            ),
        ),
        timing=RunTiming(
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            ended_at=datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
            duration_seconds=2.0,
            origin=runtime,
        ),
    )
    return plan, run


@pytest.fixture
def pair():
    return example_pair()
