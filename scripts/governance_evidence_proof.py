"""Installed-core A/B example: original documents, offline consumption and calls.

No Docker, registry, proof signer or external governance is simulated by this qualification.
Only the explicitly supplied, trusted pricing example is executed in a child.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from apizr.capabilities.model import Digest
from apizr.delivery import identity
from apizr.exposure import ExposurePolicy, plan_exposure
from apizr.graph import build_graph
from apizr.repository import scan_sources
from apizr.repository_interfaces.evidence import export_evidence, verify_evidence
from apizr.repository_interfaces.generator import render_repository_bundle
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_readiness import RepositoryReadinessPolicy, assess_repository


def exercise(examples: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    records = {}
    for variant, expected_total in (("a", 300), ("b", 350)):
        sources = {"pricing.py": (examples / variant / "pricing.py").read_bytes()}
        catalog = scan_sources(sources.items())
        graph = build_graph(catalog, sources)
        readiness = assess_repository(
            catalog,
            graph,
            policy=RepositoryReadinessPolicy.model_validate(
                {"execution": {"modes": ["direct"]}}
            ),
        )
        policy = ExposurePolicy.model_validate(
            {
                "selection": {"include": ["python:pricing:total"]},
                "interfaces": ["rest", "mcp"],
                "execution": {"allowed": ["direct"]},
            }
        )
        exposure = plan_exposure(catalog, graph, readiness, policy=policy)
        variant_dir = output / variant
        variant_dir.mkdir()
        bundles = {}
        for interface in ("rest", "mcp"):
            bundle = variant_dir / (interface + "-bundle")
            evidence = variant_dir / interface
            write_bundle(
                bundle,
                render_repository_bundle(
                    catalog,
                    graph,
                    readiness,
                    policy,
                    exposure,
                    sources,
                    interface=interface,
                ),
            )
            manifest = export_evidence(bundle, evidence, interface=interface)
            digest = identity(manifest)
            if interface == "rest":
                result = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        "-c",
                        """import json,sys
from pathlib import Path
from apizr.repository_interfaces.runtime import load_bundle
manifest, functions, loader, _ = load_bundle(Path(sys.argv[1]), 'rest')
try:
    print(json.dumps(functions['python:pricing:total'](100,2)))
finally:
    loader.close()
""",
                        str(bundle.resolve()),
                    ],
                    cwd=output,
                    capture_output=True,
                    check=True,
                    timeout=30,
                )
                assert json.loads(result.stdout) == expected_total
            # This consumer has only JSON; the original generated code is gone.
            shutil.rmtree(bundle)
            assert (
                verify_evidence(evidence, interface=interface, expected=digest)
                == manifest
            )
            bundles[interface] = digest.model_dump()
        records[variant] = {
            "capability_id": catalog.capabilities[0].id,
            "source_digest": Digest.of_bytes(sources["pricing.py"]).model_dump(),
            "catalog_digest": identity(catalog).model_dump(),
            "exposure_plan_digest": identity(exposure).model_dump(),
            "bundles": bundles,
            "observed_total_cents": expected_total,
        }
    assert records["a"]["capability_id"] == records["b"]["capability_id"]
    for key in ("source_digest", "catalog_digest", "exposure_plan_digest", "bundles"):
        assert records["a"][key] != records["b"][key]
    result = {
        "qualification": "installed core; static documents and trusted local invocation",
        "registry_executed": False,
        "external_governance_executed": False,
        "variants": records,
    }
    (output / "comparison.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--examples",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "examples/governance",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(exercise(args.examples, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
