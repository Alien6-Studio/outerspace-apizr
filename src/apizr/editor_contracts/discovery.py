"""Discover supported contracts without inspecting a project or importing SDKs."""

from importlib.metadata import version

from apizr.editor_contracts.model import EngineCapabilities, OperationCapability


def capabilities() -> EngineCapabilities:
    from apizr.scientific_providers.builtin.provider import BuiltinProvider

    return EngineCapabilities(
        engine_version=version("outerspace-apizr"),
        providers=(BuiltinProvider().descriptor,),
        operations=(
            OperationCapability(
                name="capabilities",
                result_schemas=("apizr.editor-capabilities/v1",),
                required_permissions=(),
            ),
            OperationCapability(
                name="inspect",
                result_schemas=("apizr.experiment-inspection/v1",),
                required_permissions=("source.analyze",),
            ),
            OperationCapability(
                name="experiment_list",
                result_schemas=(
                    "apizr.experiment-history/v1",
                    "apizr.experiment-history/v2",
                ),
                required_permissions=("source.analyze", "experiments.read"),
            ),
            OperationCapability(
                name="experiment_show",
                result_schemas=(
                    "apizr.experiment-record/v1",
                    "apizr.experiment-record/v2",
                ),
                required_permissions=("source.analyze", "experiments.read"),
            ),
            OperationCapability(
                name="experiment_diff",
                result_schemas=("apizr.experiment-diff/v1", "apizr.experiment-diff/v2"),
                required_permissions=("source.analyze", "experiments.read"),
            ),
            OperationCapability(
                name="plan_exposure",
                result_schemas=("apizr.exposure-plan/v1",),
                required_permissions=("source.analyze",),
            ),
        ),
    )
