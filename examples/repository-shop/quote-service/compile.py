"""Use the documented public compiler; never import the business project here."""

from pathlib import Path

from apizr.exposure import ExposurePolicy, ExposureRefused
from apizr.repository import ScanPolicy
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_readiness import RepositoryReadinessPolicy
from apizr.workspace.compiler import prepare_exposure, render_bundle
from apizr.workspace.operator_policy import load_operator_policy

root = Path(__file__).resolve().parent
operator = load_operator_policy(root / "operator.json")
readiness = RepositoryReadinessPolicy.model_validate_json(
    (root / "readiness.json").read_bytes()
)
policy = ExposurePolicy.model_validate_json((root / "exposure.json").read_bytes())
# Keep example drivers outside the business source universe.
scan = ScanPolicy(source_roots=("src",))
prepared = prepare_exposure(
    root,
    operator_policy=operator,
    readiness_policy=readiness,
    policy=policy,
    scan_policy=scan,
)
for interface in ("rest", "mcp"):
    write_bundle(
        root.parent / "python-bundles" / interface,
        render_bundle(prepared, interface=interface),
    )
print("Public selection: api.quote; rendered REST and MCP")

refused_policy = ExposurePolicy.model_validate(
    {
        "selection": {"include": ["python:unfinished:stream_events"]},
        "interfaces": ["rest"],
        "execution": {"allowed": ["direct"]},
    }
)
try:
    prepare_exposure(
        root,
        operator_policy=operator,
        readiness_policy=readiness,
        policy=refused_policy,
        scan_policy=scan,
    )
except ExposureRefused as error:
    assert error.diagnostics
    print("Refused unsupported stream:", error.diagnostics[0].code)
else:
    raise AssertionError("A streaming function must not become a JSON endpoint")
