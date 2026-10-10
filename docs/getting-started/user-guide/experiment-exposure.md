# Experiment → serving (0.4.5 development)

You reviewed a successful Run and chose the capability you want to expose.
`apizr experiment expose` binds that recorded context to Apizr's existing
repository REST or MCP bundle. Run evidence does not bypass Readiness.

```sh
apizr experiment expose <RUN> --root . --operator-policy operator.json \
  --capability python:fraud:predict --interface rest \
  --artifact model --dependency scikit-learn --dependency joblib \
  --output-dir dist/fraud-rest
```

Use `--interface mcp --output-dir dist/fraud-mcp` for the ordinary MCP tool
bundle. Exactly one capability and one interface are required. There is no
`--all-ready`, automatic `predict` selection or automatic training exposure.
Use `--format json` for the strict binding and bundle-manifest SHA-256.

## Small training-to-serving example

This core-only example creates a coefficient file during the Run.
The standard main guard keeps training out of module import. The output name
`model` is selected explicitly; the other recorded output stays private.

<!-- experiment-exposure:guide -->
```sh
cat > serving.py <<'PYTHON'
import json
from pathlib import Path

def predict(value: int) -> int:
    model = json.loads(Path(__file__).with_name("model.json").read_text())
    return value * model["multiplier"]

def train() -> None:
    Path("model.json").write_text('{"multiplier":3}')
    Path("debug.json").write_text('{"debug":true}')

if __name__ == "__main__":
    train()
PYTHON
python3 - <<'PYTHON'
import json
from pathlib import Path
root = Path.cwd()
(root / "operator.json").write_text(json.dumps({
    "schema": "apizr.operator-policy/v1",
    "grants": [{"adapter": "repository", "operation": "analyze",
                "target": {"kind": "local", "root": str(root)},
                "permissions": ["source.analyze"]}]}))
PYTHON
RUN=$(apizr experiment run serving.py --output model=model.json --output debug=debug.json --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_digest"])')
apizr experiment expose "$RUN" --operator-policy operator.json \
  --capability python:serving:predict --interface rest --artifact model \
  --output-dir dist/rest --format json > rest-binding.json
apizr experiment expose "$RUN" --operator-policy operator.json \
  --capability python:serving:predict --interface mcp --artifact model \
  --output-dir dist/mcp --format json > mcp-binding.json
```

Start these ordinary bundles using the [repository REST/MCP instructions](exposure.md).
The installed qualification calls both real transports with the same input and
checks their business responses after deleting the original project and store.

## Reviewed evidence and current files

The Run is loaded through the same validated store as `experiment show`.
`--store` selects another history directory; its default is
`ROOT/.apizr/experiments/v1`. Only `success` is admitted; failed and cancelled
Runs are refused with `run_not_successful`.

The command inspects the recorded source again, without execution. Its raw
digest must match the Run; notebooks must also retain the exact transformed
Python digest. A mismatch refuses with `run_source_changed`. The requested
capability ID must be an exact serving candidate in that source, even if another
repository capability would independently be READY. Unrelated selections refuse
with `capability_not_in_run_source`.

The Python source must also match its Catalog entry. For notebooks, Apizr builds
an explicit, bounded in-memory repository universe containing the exact
transformed Python and admitted project Python helpers. The synthetic source
path comes from the notebook's logical module, under a selected source root.
A real source-path or module collision is refused. Notebook discovery is not
enabled globally.

Catalog, Graph, Repository Readiness and ExposurePlan then decide eligibility.
Required helper ambiguity remains a blocker; unrelated unfinished modules remain
visible in the global audit without automatically blocking an independent
selection. Only the selected capability becomes a public endpoint or tool.

## Source authority and policy

An existing Run does not authorize repository reads. Supply an explicit operator
policy granting `source.analyze` for this exact local root, as for ordinary
[repository exposure](exposure.md). A project-controlled policy file is never
loaded implicitly. `--source-root`, scan limits and Graph limits use the shared
repository option validators.

The bridge's default ExposurePolicy includes only the requested capability and
interface, excludes none, disables `include_all_ready`, and permits only direct
execution. Its default RepositoryReadinessPolicy selects the same direct mode.
`--readiness-policy` accepts the existing independent policy contract; its
requirements are preserved. CONDITIONAL remains refused by default.
`--allow-conditional` requests the existing explicit conditional semantics; it
cannot waive incomplete required evidence, initialization blockers or unsupported
interfaces.

Shared Readiness recognizes the exact top-level `if __name__ == "__main__":`
guard as inert when importing a module whose logical name is not `__main__`.
The guard must have no `else`; `__name__` must not be rebound, and namespace
mutation or indirect attribute/subscript writes prevent this proof. Other guard
forms stay conservative. Imports, declarations and other required evidence are
still assessed, including those found inside the guard. The source is retained
verbatim in the bundle. This is a shared import-time refinement, not permission
to ignore training initialization or to expose a CONDITIONAL capability.

## Select resources by recorded name

`--artifact model` means the exact `OutputArtifact.name` in the selected Run.
Repeat the option for additional resources. Only selected Run outputs are
packaged, and their current bytes must still match the recorded Run digest.
The bridge verifies SHA-256 and recorded size using bounded, descriptor-relative
regular-file reads with `O_NOFOLLOW`, no symlink parents and change detection.
It rechecks the retained bytes before rendering. Missing references, missing or
changed files, duplicate selections, symlinks and special files are refused.

The existing ApplicationInputs contract remains authoritative:

- At most 128 resources, 16 MiB per resource and 32 MiB combined.
- Portable references are preserved as `source/<reference>`; rejected paths are
  not renamed. No absolute paths, traversal or hidden application resource paths.
- Application dependencies are separate in `application-requirements.txt`.

Serving code uses the existing source-relative resource layout, for example
`Path(__file__).with_name("model.json")` for a root module and root resource.
The bridge hashes bytes only; it does not call pickle, joblib, torch or ONNX
loaders. Trusted serving code remains responsible for runtime model loading.

The binding establishes that these resources were explicitly selected for this
bundle. It does not establish that a resource caused the function's predictions,
or that every recorded output was created by the Run rather than observed at its
completion boundary.

## Select dependencies from the Run

`--dependency scikit-learn` uses the exact version observed in that Run, producing
`scikit-learn==<observed-version>`. Repeat the option for other distributions.
Only selected packages enter the bundle. Unknown packages or versions, duplicate
normalized names, requirement expressions and URLs are refused. No PyPI lookup,
installation, resolution or current-environment version fallback occurs.
Existing ApplicationInputs exact-pin syntax and the 128-dependency limit apply.

Run-bound application resources currently use Apizr's direct repository service
bundle. Governed local-process/OCI application resources remain refused by the
existing contract. Larger serving resources need a separate future design.

## Portable evidence and verification

`experiment-exposure.json` has schema `apizr.experiment-exposure/v1`. It links
the exact Run and Plan, Run source identity, repository/Catalog/Graph/Readiness,
ExposurePlan and RepositoryInterface digests, explicit capability/interface,
selected OutputArtifact records, exact dependency pins and ApplicationInputs
digest. It contains no timestamp, random ID or absolute output path.

Its SHA-256 is included in the normal bundle manifest's `artifacts`. Normal
startup verifies its exact bytes, together with the interface, exposure plan and
selected resource bytes. `apizr expose export` preserves the attachment;
`apizr expose verify` verifies its bytes against the reviewed manifest digest.
The pure `validate_exposure_binding` API additionally checks the domain links
against a RunRecord, RepositoryInterface, ExposurePlan and ApplicationInputs.

The generated server requires neither the original research tree nor the
experiment store. The store, other Runs and comparison artifacts are not copied.
No training re-execution or replacement Run is created on mismatches. Compilation
performs no network request, artifact upload, signature or Attest invocation.

Apizr binds the Run to the compiled serving bundle. Organizational promotion and
approval remain external. This command does not create a registry entry, owner,
stage, approval or external governance identity.
