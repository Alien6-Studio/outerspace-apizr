# Inspect static capability relationships

Use `apizr graph` to see which Python modules import each other and which direct
capability calls can be resolved from static source evidence:

```bash
apizr graph . --source-root src
apizr graph . --source-root src --format json
apizr graph . --source-root src --graph > capability-graph.json
```

`--graph` emits canonical `apizr.graph/v1` JSON. `--format json` wraps that graph
with its digest and derived statistics. The default human report lists up to 20
relationship occurrences and 10 graph diagnostics; `--details` expands it.

For example:

```python
from shop.pricing import calculate as total


def checkout(value: int) -> int:
    return total(value)
```

If `shop.pricing.calculate` is a uniquely identified capability with a stable
binding, the graph records separate facts: a module import, a capability-symbol
import and a possible direct call from `checkout` to `calculate`. Importing a
function without calling it produces no call edge. Returning or passing the function as a
value produces a distinct `references_capability` relationship, never a call edge.

An import is not proof of invocation. A resolved call expression is evidence of
a **possible direct call**, not proof that the branch executes or the call succeeds.
External imports use lexical module names; the scanner does not check installed
packages. Dynamic imports and ambiguous aliases retain uncertainty.

## Source roots and bounds

The command supports the same scan options as [`apizr scan`](scan.md): repeated
`--source-root`, additive `--exclude-dir`, `--max-file-bytes`,
`--max-source-files`, `--max-total-bytes`, `--max-entries` and `--max-depth`.
Source discovery runs once, and both Catalog and Graph use those exact bytes.
The Catalog artifact format is unchanged.

Graph-specific aggregate limits are:

```bash
apizr graph . --source-root src \
  --max-ast-nodes 500000 --max-relationships 50000 \
  --max-calls 50000 --max-imports 10000
```

If a limit is exceeded, the graph is incomplete and all relationships are
discarded. It does not return a misleading partial relationship prefix.

Exit status:

| Status | Meaning |
| --- | --- |
| `0` | Graph produced without blocking Catalog/Graph diagnostics |
| `1` | Artifact produced, but blocking ambiguity, unavailable analysis or resource limit remains |
| `2` | Invalid root, policy or source linkage prevented graph construction |

External imports alone do not fail the command. Use `apizr scan --details` to
inspect underlying Catalog/Readiness diagnostics when its exit status is blocking.
Filesystem scanning currently supports Linux and macOS; no Docker is needed.

## Trust and limits

Graph construction never imports your modules, evaluates decorators, annotations
or defaults, executes `setup.py`/build backends, installs dependencies, calls Git,
starts Python subprocesses or accesses the network. It does not make execution
of that code safe.

Local shadowing, rebinding, star imports and ambiguous module identities prevent
unsupported call claims. Nested function/class/lambda bodies are not attributed
to the enclosing capability. Calls through arbitrary objects, assigned function
values or callbacks are not resolved. No effects, permissions or readiness are
propagated through the graph.

See the [Graph architecture](../../architecture/capability-graph-v1.md) for exact
resolution rules, evidence, diagnostics, canonical artifacts and in-memory APIs.
