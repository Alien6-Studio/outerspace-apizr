# Capability IR v1 verification record

!!! note "Historical engineering record"

    These results describe the Capability IR v1 change at the recorded revision; they are not live CI status.
    See the [archive index](records.md), [current migration guidance](../getting-started/developer-guide/releases.md)
    and [current security baseline](security-baseline.md) for context.

Baseline: `a386f507000852ab19e8239f6cbc8b4b3b8d249a`. This record concerns local
verification from a clean index export, not a claim about a future GitHub run.
The normative contract is [Capability IR v1](capability-ir-v1.md).

## Architecture and contracts

1. **Architecture:** independent source → AST → typed IR. The legacy pipeline
   remains unchanged and does not import the IR. The core imports only stdlib and
   Pydantic; a subprocess test checks that generation frameworks are not loaded.
2. **Modules:** `apizr.capabilities` contains `model.py`, `types.py`, `analyzer.py`,
   `serialization.py` and its public exports. Diagnostics live with the domain
   models. `apizr.capability_notebooks` owns the existing notebook exporter adapter
   outside the core. New tests live under `tests/capabilities/`.
3. **Schema:** `apizr.capability/v1`, independent of the unchanged package version.
4. **Identity:** `python:<logical-module>:<symbol>`, no filesystem-derived identity.
   Models reject duplicates and inconsistent symbol/module references.
5. **Source digest:** SHA-256 over exact input bytes; string API input means UTF-8.
   Encoding-cookie, BOM, CRLF and Unicode cases are tested.
6. **Canonical representation:** sorted JSON keys, compact separators, explicit
   nulls/defaults, UTF-8 without ASCII escaping, deterministic collection ordering,
   exactly one terminal LF. Signature/decorator/overload order is meaningful.
7. **Document digest:** SHA-256 of canonical bytes, returned separately from the
   hashed document. No attestation formats or dependencies.
8. **Parameters:** binding kind, required/default presence, declaration and safe
   unevaluated default expression; variadics are explicitly rejected.
9. **Types:** complete `ast.unparse` expression plus syntax classification and
   declared evidence. Literal values, forward names, nested members and annotation
   metadata survive; no runtime resolution is attempted.
10. **Execution:** sync, async, generator and async-generator, with scope-aware
    yield detection. No return enforcement is promised.
11. **Effects:** all eight categories default to unknown, never false by absence
    of evidence. No effect inference is implemented.
12. **Evidence:** declared / observed / inferred / unknown are distinct enum values.
13. **Diagnostics:** APIZR-CAP-001 duplicate, 002 variadic, 003 control flow,
    004 overload ambiguity, 005 binding/unsupported lambda, 006 unknown type
    structure. Severity and logical source locations are structured.
14. **Duplicates:** error and omission of the ambiguous symbol, no first/last choice.
15. **Overloads:** conservatively evidenced typing markers, consecutive declarations
    and one concrete implementation; contracts retained, no dispatch. Ambiguous
    association produces an error, including rebinding and conditional groups.
16. **Conditional definitions:** retained with unknown availability and a warning.
    Decorators also preserve uncertainty. Unconditional means lexical placement,
    never proof of runtime availability.
17. **Notebooks:** original notebook bytes and exact exported Python UTF-8 bytes
    have separate digests. Locations refer to exported Python. No kernel execution.
18. **Golden:** `tests/fixtures/capability_ir/v1/basic.py` and `basic.json`, covering
    ordinary/async, positional-only/keyword-only/defaults, Literal/Union, docstring
    and returns. The JSON was reviewed against those two source definitions.
19. **JSON Schema:** `docs/specs/apizr-capability-v1.schema.json`, generated from
    Pydantic and compared byte-for-byte with fresh schema output in tests.
20. **Properties:** deterministic bytes, unrelated-directory independence, stable
    logical IDs despite formatting, hostile source non-execution and unique IDs
    with deterministic duplicate diagnostics. Existing characterization corpora
    are reused with separate IR expectations; old expectations are unchanged.

## Results

21. **Core coverage:** 99.20% branch-aware on Python 3.14 (381 statements, 118
    branches, four unvisited branch destinations); 99.24% on 3.11–3.13. All core
    statements execute; model/types/serializer/digest coverage is 100%. The four
    unvisited alternatives concern empty exception/match binding names and a
    non-lambda annotated assignment. Notebook adapter coverage is 100%. CI adds a
    core-specific 90% floor; the global 55% floor remains unchanged.
22. **Tests and total coverage:** baseline 246 passed, 65.95% on Python 3.14;
    final 397 passed, 72.96% on Python 3.14, including all 246 historical tests.
    The 151 new parameterized cases/property tests protect concrete contracts.
    Two existing dependency deprecation warnings remain.
23. **Compatibility:** 397 passed on each of 3.11, 3.12, 3.13 and 3.14. Total
    coverage is 73.40% on 3.11–3.13; interpreter differences in executable-line
    accounting change the denominator. Pyright passes, with strict checking of
    the new core. Ruff lint/format and all pre-commit hooks pass. MkDocs strict
    build passes. Wheel and sdist build successfully.
24. **Audit:** zero vulnerabilities in the resolved runtime (72), development (30),
    docs (30) and security-tooling (29) dependency sets. No dependency or lockfile
    changes. The existing CodeQL and security workflows remain enabled.
25. **Legacy bytes:** generated both the pricing notebook and its baseline-exported
    Python source using the original baseline archive and the new clean export,
    explicitly targeting Python 3.11. All 14 generated files have identical
    SHA-256 values and relative filenames. No legacy production file changed.
26. **Wheel/container:** installed wheel tested outside the checkout on Python
    3.11 and 3.14, including `import apizr`, absence of `src`, resources/license,
    CLI help, notebook generation and the new IR API/hash. Container smoke tests
    pass for 3.11 and 3.14 (health, representative calculation, non-root process).
    Existing CI retains container targets 3.11–3.14.
27. **Commands:** the exact validation commands and environment are below. Initial
    attempts identified a pytest module-name collision (fixed by packaging the new
    test directory), a Ruff-formatted documentation code block, and `/tmp` versus
    `/private/tmp` normalization in the external legacy-comparison harness. Their
    affected checks were rerun successfully; no gate was weakened.
28. **Diff:** the final review report includes the exact `git diff --stat` output.
    Only new IR/adapter/tests/specification/schema and scoped tooling/docs changes
    are included. No files are removed or moved; no historical fixtures change.
29. **Deferred:** binding/dataflow analysis and runtime readiness (#31), classes,
    variadics, type resolution, effect inference, generator consumers and runtime
    enforcement. The existing argparse interface has required mutually exclusive
    input flags; CLI subcommand design is deferred to preserve that interface.
    Python inspection/serialization APIs are provided now. Historical issue #28
    remains open because its legacy behavior is unchanged. No REST/MCP/Attest or
    website work is included.

## Exact validation commands

Working directory for final checks: `/tmp/apizr-ir-v1/clean`, created with
`git checkout-index --all --prefix=/tmp/apizr-ir-v1/clean/`, followed by `git init`
and `git add .` in that directory so pre-commit includes new files. Environment:

```sh
export UV_CACHE_DIR=/tmp/apizr-uv-cache
export PRE_COMMIT_HOME=/tmp/apizr-pre-commit
export UV_PYTHON_INSTALL_DIR=/tmp/apizr-python
export UV_PYTHON=3.14

uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest --cov --cov-report=term-missing --cov-report=json:/tmp/apizr-ir-v1/final/coverage-clean.json
uv run coverage report --include='src/apizr/capabilities/*' --fail-under=90
uv build
uv run pre-commit run --all-files
uv run --group docs mkdocs build --strict
uv run python scripts/smoke_wheel.py dist/*.whl --python 3.11
uv run python scripts/smoke_wheel.py dist/*.whl --python 3.14
uv run python scripts/smoke_container.py --python-version 3.11
uv run python scripts/smoke_container.py --python-version 3.14
uv run --group security python scripts/audit_dependencies.py --output /tmp/apizr-ir-v1/final/audit-clean.json
```

For each of `3.11`, `3.12`, `3.13`, the following commands also ran in that clean
export, with `UV_PYTHON` set to the respective version,
`UV_PROJECT_ENVIRONMENT=/tmp/apizr-ir-v1/py311` (or `py312` / `py313`) and
`COVERAGE_FILE=/tmp/apizr-ir-v1/final/.coverage-3.11` (or `.coverage-3.12` / `.coverage-3.13`):

```sh
uv sync --locked
uv run pytest --cov --cov-report=term-missing
uv run coverage report --include='src/apizr/capabilities/*' --fail-under=90
```

Baseline commands ran in the unchanged original checkout, with the same uv cache:

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pyright
COVERAGE_FILE=/tmp/apizr-ir-v1/baseline/.coverage uv run pytest --cov --cov-report=term-missing --cov-report=json:/tmp/apizr-ir-v1/baseline/coverage.json
uv run --group security python scripts/audit_dependencies.py --output /tmp/apizr-ir-v1/baseline/audit.json
```

The separate legacy comparison used:

```sh
git archive a386f507000852ab19e8239f6cbc8b4b3b8d249a | tar -x -C /tmp/apizr-ir-v1/baseline/source
PYTHONPATH=/tmp/apizr-ir-v1/baseline/source/src .venv/bin/python /tmp/apizr-ir-v1/legacy_generate.py /tmp/apizr-ir-v1/baseline/source /tmp/apizr-ir-v1/baseline/generated
# From the clean export:
.venv/bin/python /tmp/apizr-ir-v1/legacy_generate.py /tmp/apizr-ir-v1/clean /tmp/apizr-ir-v1/final/generated
diff -u /tmp/apizr-ir-v1/baseline/generated-hashes.json /tmp/apizr-ir-v1/final/generated-hashes.json
```

The comparison helper asserts that `apizr.__file__` belongs to the intended tree,
invokes `convert(input, output, python_version='3.11')` for the two inputs, and
hashes every generated file in sorted relative-path order. `PYTHONPATH` is used
only to select the archived baseline in this external comparison, never by the
package, tests or installed-wheel checks.
