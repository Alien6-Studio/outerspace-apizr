<span id="annotation-compatibility-matrix"></span>
<span id="discovery-and-signatures"></span>
<span id="explicitly-rejected"></span>
<span id="future-candidate"></span>
<span id="how-to-interpret-the-contract"></span>
<span id="import-inference-and-files"></span>
<span id="legacy-behavior-contract"></span>
<span id="legacy-observed-design-decisions-required"></span>
<span id="property-tests-and-mutation-resistance"></span>
<span id="runtime-behavior"></span>
<span id="small-safetycorrectness-fixes-made-after-reproducing-failures"></span>
<span id="source-notebooks-and-execution-boundary"></span>
<span id="starting-evidence"></span>
<span id="supported"></span>
<span id="verification-record"></span>

# Historical pipeline behavior — removed in 0.4.6

This page records retired behavior for migration, not a supported runtime contract.
The notebook/script → AST metadata → FastAPI → Docker pipeline, its ASGI upload
service and step plugins were removed in 0.4.6. Use the
[complete migration table](../releases/migrate-0.4.6.md#removed-generation-pipeline).

The pre-removal characterization, limitations and measurements remain accessible
in the [0.4.5 source](https://github.com/Alien6-Studio/outerspace-apizr/blob/v0.4.5/docs/architecture/legacy-behavior-contract.md).
They do not describe current compiler eligibility, execution or exposure policy.
The deprecation commit retains passing pipeline/HTTP/plugin characterizations
before removal; retired-only tests no longer run against the new engine.
Shared modern compiler characterization JSON remains in its original fixture tree.

The retained notebook exporter belongs to `apizr.notebooks`. Eighteen notebooks
have immutable pre-move inputs and expected Python exports/formatting, including
an unchanged magic refusal. Current source admission, cell selection, non-execution
and mutation controls still apply. No modern coverage or security floor is removed;
only the separate 59.5% floor for deleted `src/apizr/modules` is retired.
