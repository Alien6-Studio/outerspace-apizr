# Inventory a Python project

`apizr scan` discovers Python files under explicit source roots, derives stable
logical module names and reuses single-source inspection. It does not import or
execute project code, install packages, use Git or access the network. Filesystem
scanning v1 supports Linux/macOS. No Docker is required.

```sh
apizr scan .
apizr scan . --source-root src
apizr scan . --source-root packages/core/src --source-root packages/tools/src
```

Without `--source-root`, the repository directory itself is the source root.
For `src/project/pricing.py`, selecting `src` gives module `project.pricing`.
`src/project/__init__.py` gives module `project`. Selecting a package directory
itself as a source root leaves its top-level `__init__.py` without a logical name;
select the package's parent instead. Parent package marker files are not required.
This is lexical inventory, not proof that importing the package would work.

Source roots are sorted and must not overlap or escape the repository. Two files
with the same logical module are errors; neither contributes catalog capabilities.
Invalid files remain visible and do not prevent independent valid files being
inspected. Readiness limitations and rejected declarations remain in each source's
Inspection. The catalog introduces no new readiness policy.

## Output and exit codes

```sh
apizr scan . --source-root src --details
apizr scan . --source-root src --format json
apizr scan . --source-root src --catalog
```

The default human report limits displayed sources/diagnostics; `--details` expands
it. `--format json` emits the complete catalog, its digest and derived statistics.
`--catalog` emits only canonical `apizr.catalog/v1` JSON, suitable for byte comparison
and hashing. Redirect stdout outside the scanned tree to save it without changing
scan inputs. Repository location and timestamps are not catalog identity fields.

- **0:** completed without blocking inventory/IR errors or ambiguous declarations.
  Conditional or unsupported readiness alone does not fail a scan.
- **1:** catalog emitted with blocking diagnostics; inspect its source records.
- **2:** arguments/policy or repository location prevented a valid scan.

An invalid individual source root appears in a catalog with exit 1. Missing whole
repository roots return 2. Warnings such as skipped symlinks do not fail a scan.

## Exclusions and limits

The scanner includes `tests`. It ignores `.git`, `.venv`, `venv`, `__pycache__`,
`.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `dist`, and `build` directories by
exact basename. It does not interpret `.gitignore` or package build configuration.
Only `.py` files are selected; repository notebooks are deferred. Existing
`apizr inspect notebook.ipynb` remains available.

```sh
apizr scan . --exclude-dir tests --exclude-dir generated
apizr scan . --source-root src --max-file-bytes 1048576 --max-source-files 1000
```

Other bounds are `--max-total-bytes` (default 16 MiB), `--max-entries` (20,000) and
`--max-depth` (64). Default per-file size is 1 MiB. Exceeding a per-file limit
records that file without reading it and continues; exceeding a global limit
returns a blocking diagnostic and discards the partial inventory. No partial
prefix is presented as a complete project.

Symlinked files/directories are not followed, even when they point inside the
repository. No arbitrary target path is emitted in diagnostics. Use a stable tree
for repeatable scans; concurrent filesystem mutation is not an atomic snapshot.

Moving an identical tree keeps module/capability IDs and catalog bytes unchanged.
Moving a module within a source root changes its logical identity. Repository
identity covers the **selected scan universe**, including policy/discovery results,
not all files and not Git history. Source/Inspection, policy, repository and catalog
have independent digests.

See the [scanner contract](../../architecture/repository-scanner-v1.md) for schemas,
diagnostic codes, exact bounds and hashing rules. A capability graph and import
resolution are future work; the catalog does not contain dependency or call edges.
