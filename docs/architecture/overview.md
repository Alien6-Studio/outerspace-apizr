# Capability Compiler architecture

Apizr 0.2.0 discovers capabilities in existing Python software, describes what is
statically known, and generates interfaces for eligible contracts.

```text
Python repository → Scanner → Capability Catalog → Capability Graph
Scripts / notebooks ──────────────→ Capability IR + static readiness
Catalog + Graph ─────────────────→ Repository Readiness (policy evidence)
Capability IR + static readiness → Interface Contract → REST / MCP
                                                          ↓
                                      direct or governed execution
                                             local-process / OCI
```

## Discover and describe

The [scanner](repository-scanner-v1.md) inventories Python files under bounded
source roots. [Capability IR](capability-ir-v1.md) records declarations and typed
contracts; [the graph](capability-graph-v1.md) adds statically established
relationships. Individual inspection also accepts notebooks. No input is
imported or executed during these operations.

## Assess evidence

[Static readiness](capability-readiness-v1.md) assesses individual interface
contracts. [Repository Readiness](repository-readiness-v1.md) combines catalog,
graph and policy evidence, preserving declaration-level results and unknowns.
It does not test runtime availability or grant access. `READY` never means safe.
Imports are not calls, discovery is not trust, and unknown effects remain unknown.

## Generate interfaces

[REST](rest-generator-v1.md) and [MCP](mcp-generator-v1.md) consume shared
[interface semantics](../getting-started/user-guide/mcp.md). Contracts precede
transports. Deterministic artifacts and digests support review and comparison;
they are attestable evidence, not signed attestations.

## Execute explicitly

A direct server imports and invokes trusted source in its own process.
[Governed transports](governed-transport-runtime-v1.md) opt into an
[execution policy](execution-policy-v1.md), separately from readiness policy.

- **Local-process:** a fresh process with time, input/output and environment
  limits. No host filesystem or network isolation.
- **OCI-container:** Linux container namespaces and resource controls with a
  trusted Docker daemon and explicit worker image. Not a VM boundary.
- **Unsupported:** absolute subprocess prohibition, arbitrary untrusted-code
  hosting, automatic trust decisions and an enterprise control plane.

Execution remains experimental: the contracts and refusal paths are tested,
but the supplied backends require trusted code and operational prerequisites.
See [OCI execution](oci-container-runtime-v1.md) and
[governed OCI transports](governed-oci-transports-v2.md).

## Compatibility and limits

Top-level Python functions are the capability unit. Classes/methods, dynamic
binding and effects are not automatically resolved. Repository scanning is
Python-only; notebook support belongs to individual inspection/generation.
The [legacy pipeline](../getting-started/user-guide/apizr.md) is independent and
retained for compatibility, including its documented
[behavior and limitations](legacy-behavior-contract.md).

Historical verification measurements live in the [engineering archive](records.md).
They describe their recorded revisions rather than promising current test counts.
