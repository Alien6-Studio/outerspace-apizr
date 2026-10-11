"""Direct fictional records: no store, files or execution needed for comparison."""

from apizr.experiments import ExperimentRun, plan_digest, run_digest
from apizr.experiments.store import RunRecord

from .conftest import example_pair


def replace(model, **changes):
    return type(model).model_validate(
        {k: getattr(model, k) for k in type(model).model_fields} | changes
    )


def record(plan=None, run=None, **changes):
    default_plan, default_run = example_pair()
    plan = plan if plan is not None else default_plan
    run = run if run is not None else default_run
    run = ExperimentRun.model_validate(
        {k: getattr(run, k) for k in type(run).model_fields}
        | changes
        | {"plan_digest": plan_digest(plan), "subject": plan.subject}
    )
    return RunRecord(
        plan=plan, run=run, plan_digest=plan_digest(plan), run_digest=run_digest(run)
    )
