# Repository Scanner and Capability Catalog v1

The scanner inventories explicitly selected Python source units and orchestrates
existing `Inspection v1`. It does not resolve imports, infer calls or readiness,
execute code, install dependencies or inspect Git metadata. No transport or
execution backend is involved.

```text
Repository / Python project
           ↓
Repository Scanner (scan/v1)
           ↓
Source units → existing Inspection v1
           ↓
Capability Catalog (catalog/v1)
           ↓
Capability Graph (graph/v1; separate consumer)
           ↓
Repository Readiness / Policy Analysis
```

## Contracts and APIs

`apizr.scan/v1` versions discovery policy independently of `apizr.catalog/v1` and
the Apizr package version. Generated schemas are
[ScanPolicy](../specs/apizr-scan-v1.schema.json) and
[Catalog](../specs/apizr-catalog-v1.schema.json). Tests compare committed schemas
with typed model schemas and validate the canonical fixture.

```python
from apizr.repository import (
    ScanPolicy,
    scan,
    scan_sources,
    catalog_bytes,
    catalog_digest,
)

policy = ScanPolicy(source_roots=("src",))
catalog = scan("/deployment/project", policy=policy)
canonical = catalog_bytes(catalog)
identity = catalog_digest(catalog)

# In-memory manifests share the same inspection/catalog assembly, without a VFS.
virtual = scan_sources([("src/project/api.py", b"def run(): return 1")], policy=policy)
```

`policy.py` defines discovery; `modules.py` derives lexical identities;
`discovery.py` handles bounded filesystem reads; `scanner.py` assembles existing
Inspections. `model.py` checks catalog references/indexes and derives statistics;
`serialization.py` defines canonical bytes and independent digests;
`reporting.py` presents results. None imports FastAPI, MCP, Docker, generators or
execution backends. Notebook discovery and lexical import inventories are deferred.

## Roots, paths and modules

The explicit repository root is an input location, never a serialized identity.
All paths in scanner-owned catalog fields are relative POSIX paths. Existing
Inspection declarations/docstrings retain their original contract; source code
may itself declare arbitrary strings, including paths.

Source roots default to `.`. Supplied roots are normalized, deduplicated and
sorted. Absolute paths, parent traversal and Windows drive/backslash paths are
rejected. Roots must be disjoint: `.` with `src`, or `src` with `src/package`, is
rejected even if the current tree happens to be empty. Reordering repeated CLI
flags does not affect identity. Explicit roots are not inferred from packaging
metadata, `.gitignore` or build backends.

Module identity is relative to the selected source root:

| Root | Path | Module |
| --- | --- | --- |
| `src` | `src/project/pricing.py` | `project.pricing` |
| `src` | `src/project/__init__.py` | `project` |
| `.` | `project/pricing.py` | `project.pricing` |

Every filesystem module segment must satisfy existing Capability IR logical-module
rules, including NFKC normalization and keyword rejection. A filename containing
a dot before `.py` is not expanded into invented package segments. An
`__init__.py` directly at a source root has no lexical package name and is an
invalid-module diagnostic; selecting its parent gives it a proper package identity.
Invalid names are not renamed. Namespace-like directories without `__init__.py`
are supported lexically, without claiming runtime import correctness.

All source units mapping to the same logical module are diagnosed, including
`name.py` versus `name/__init__.py`, distinct source roots and Unicode normalization
collisions. None of those units carries an Inspection or contributes capabilities.
The catalog validator also rejects duplicate source paths, duplicate capability
IDs, inconsistent indexes/digests and manually supplied trusted collision entries.

## Discovery defaults and limits

Only `.py` is supported. `tests` is included. Exclusions are **exact directory
basenames**, not globs. Defaults are `.git`, `.venv`, `venv`, `__pycache__`,
`.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `dist`, `build`. An explicitly chosen
source root is traversed; exclusions apply to its descendants. Non-Python regular
files are ignored. Excluded directories are not traversed or hashed.

| Policy field | Default | Allowed range |
| --- | --- | --- |
| `max_file_bytes` | 1,048,576 | 1–16,777,216 |
| `max_source_files` | 1,000 | 1–100,000 |
| `max_total_bytes` | 16,777,216 | 1–268,435,456 |
| `max_entries` | 20,000 | 1–1,000,000 |
| `max_depth` | 64 below each source root | 1–128 |

The extra aggregate-byte, directory-entry and depth limits bound discovery beyond
individual source files. Entries are counted before buffering/sorting them,
including non-Python and excluded entry names, but not excluded directory contents.
Source candidates are counted before reading. Oversized files are not read; their
observed size is recorded, with no digest or Inspection. Other independent files
continue. Global count/byte/entry/depth exhaustion discards the inventory and
returns one blocking limit diagnostic; no arbitrary truncated prefix is trusted.
The in-memory API bounds consumption too. It rejects duplicate input paths.

These are input/traversal bounds, not a process sandbox or hard CPU/memory quota.
Invalid Python/encoding and parser recursion errors are localized to a source.
Raw exception text, tracebacks and offending source excerpts are never copied to
repository diagnostics. The existing Inspection's own declarations and diagnostics
remain unchanged when inspection succeeds.

## Filesystem containment and portability

V1 filesystem scanning requires POSIX descriptor-relative traversal (Linux/macOS).
There is no Windows fallback that silently weakens containment; unsupported hosts
return an operational error. In-memory `scan_sources` has no filesystem dependency.
The existing single-source commands are unaffected.

The explicitly supplied repository location anchors traversal. Its final component
must be a non-symlink directory. Each source-root component, descendant directory
and source file is opened relative to its parent descriptor with `O_NOFOLLOW`.
Source links are skipped, including loops, links to internal files and external
escapes; targets are never resolved into catalog data. Excluded directory names
also exclude same-name symlink entries. FIFOs/devices are not read. Nonblocking
file opening plus regular-file verification protects against replacement races.

Reads are byte-bounded; size/mtime/ctime comparisons around the read detect
ordinary concurrent edits. These metadata are used only to validate the read and
are never serialized. A concurrently modified tree is not an atomic filesystem
snapshot, and a privileged actor can still mutate open files. Use a stable tree
for reproducible catalogs. No source or cache is written into the repository.

Names not representable as canonical UTF-8 relative paths (for example undecodable
filesystem bytes or backslashes) produce a containing-directory diagnostic; their
raw names are not serialized and they are not read. Other invalid Python module
names retain their complete source unit with an invalid-module diagnostic.

## Source and capability records

Each source unit retains path, source root, logical module (or null), exact byte
digest and size where readable, package-marker flag, full Inspection and its
canonical digest where valid. Read failures retain the source path with null
unavailable facts. This makes the catalog self-contained for offline inspection.

Capability entries are verified indexes over source Inspections: ID, module,
source path/digest, IR/readiness digests, readiness state, interface eligibility,
execution form and source span. The scanner does not infer eligibility. Rejected
or ambiguous declarations absent from IR remain visible in the source's Readiness
assessments and IR diagnostics. Counts of assessments can therefore exceed counts
of indexed capabilities.

Statistics are derived properties, not independently stored catalog counters.
The CLI JSON envelope includes them: sources, inspected sources, capabilities,
assessments, readiness counts, repository diagnostic severity counts and affected
source count. There is no readiness percentage or weighted score.

## Repository diagnostics and exit status

Catalog diagnostic records contain stable code, relative path, optional line and
optional limit kind. Code determines severity and fixed explanatory message; raw
operating-system/parser messages are not machine semantics.

| Code | Meaning | Severity |
| --- | --- | --- |
| APIZR-REPO-001 | Invalid/unrepresentable module path | error |
| APIZR-REPO-002 | Duplicate logical module | error |
| APIZR-REPO-003 | Unreadable, changing or nonregular source/directory | error |
| APIZR-REPO-004 | Source exceeds per-file byte limit | error |
| APIZR-REPO-005 | Global scan limit; inventory discarded | error |
| APIZR-REPO-006 | Symlink skipped | warning |
| APIZR-REPO-007 | Missing/inaccessible/symlink source root | error |
| APIZR-REPO-008 | Syntax/parser failure, including invalid encoding cookies | error |
| APIZR-REPO-009 | Decoding/codec failure | error |
| APIZR-REPO-010 | Inspection recursion bound reached | error |

CLI exit **0** means the scan completed without repository errors, IR errors or
ambiguous assessments. Conditional/unsupported readiness alone is not an inventory
failure. **1** means a valid catalog was produced with those blocking conditions;
its JSON is still emitted. **2** means invalid arguments/policy or an unusable
repository anchor prevented a scan. An invalid individual source root is a catalog
error (1), preserving results from independent valid roots.

## Digests and canonical bytes

Policy, repository and catalog have separate SHA-256 identities. Canonical JSON
uses sorted keys, UTF-8, compact separators, explicit defaults, finite values and
one final LF. Source roots/exclusions are sets normalized to sorted tuples.
Sources sort by path, capabilities by ID, repository diagnostics by
path/line/code/limit. Inspection retains its existing canonical contracts.

The repository digest hashes an `Inventory` manifest containing the scan-policy
digest, sorted source `(path, module, exact-byte digest or null)` records, and
sorted discovery diagnostics. Parser/encoding/inspection failures do not enter
that manifest: their exact input bytes already identify the source. Discovery
failures and symlink facts do enter it, so an incomplete or skipped universe is
not silently equated with a clean inventory. Unavailable facts are not invented.

The **repository digest identifies the scanned source universe, not the complete
filesystem tree**. It is not a Git commit hash. Policy changes alter repository
identity even when selected source bytes overlap. Excluded content changes do not.
`catalog_digest` hashes the complete canonical catalog, including per-source
Inspections and diagnostics. It is returned separately and never hashes itself.
Inspection digests use existing `apizr.inspection.json_bytes`.

## Compatibility and evidence

Reviewed projects cover src/root layouts, namespace paths, collisions, syntax
errors and invalid/Unicode names. `tests/fixtures/catalog/v1/catalog.json` is the
catalog-v1 compatibility anchor. Property tests compare repository moves,
enumeration orders, selected/excluded mutations, policy changes and module moves.
Fresh-process audit hooks reject project imports/execution, network, subprocesses
and writes; hostile setup/decorator/default/top-level expressions are only analyzed.

Golden catalog/schema tests run on Python 3.11–3.14. Existing single-source Python
grammar support remains interpreter-dependent; v1 does not implement a separate
cross-version parser. The common-syntax golden corpus is identical on all four.
Filesystem filename codepoints are preserved rather than silently renamed.

Existing IR, Inspection, Readiness, REST/MCP, policy/runtime, direct/local/OCI and
legacy artifact contracts are unchanged. Lexical import inventory and relationship
resolution belong to the separate [Capability Graph v1](capability-graph-v1.md)
consumer. Repository generation/execution, notebook discovery, Windows filesystem
traversal and SCM provenance remain deliberately outside the scanner.
