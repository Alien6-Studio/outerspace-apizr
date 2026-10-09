---
title: Inspect Python source
description: Inspect a Python file or notebook, understand readiness states and decide which functions to expose.
---

# Inspect source without running it

Use `apizr inspect` to inspect one Python file or notebook before deciding how to
expose its functions. Inspection reads declarations and reports the static evidence
for an interface contract. It does not generate an API or run the source.

```sh
apizr inspect example.py
apizr inspect examples/pricing.ipynb
```

The default report shows logical source identity, source and IR digests, each
capability's readiness, execution form, input/return limitations, unknown effects,
and stable reason codes. Ordinary syntax or file errors appear on stderr.

<details open markdown="1">
<summary>Watch: Inspect a project and understand readiness · 4:11</summary>

Follow doctor, scan and inspect on the Requests project, then understand why a function can be refused.

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=Ypgp8fCof0E" data-apizr-video="Ypgp8fCof0E" data-apizr-title="Inspect a project and understand readiness" aria-label="Play: Inspect a project and understand readiness">
    <img src="../../../assets/videos/tutorial-inspect.jpg" width="480" height="360" loading="lazy" alt="Inspect a project and understand readiness — Alien6 Studio tutorial" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

English · [Open on YouTube](https://www.youtube.com/watch?v=Ypgp8fCof0E) ·
[Alien6 Studio](https://www.youtube.com/@Alien6Studio).
Use the written steps for the current release; a recording may show an earlier version.

</details>

## Read the result

| State | What it means |
| --- | --- |
| `ready` | Enough static contract evidence to describe an ordinary JSON/value interface |
| `conditional` | Binding, initialization, dependencies or input semantics remain uncertain |
| `unsupported` | A contract needs an adapter this policy does not define, such as streaming or Callable inputs |
| `ambiguous` | Static evidence cannot select one coherent callable contract |

`can_generate_interface` is true only for a `ready` IR capability. It is not
permission to execute code. Effects remain unknown, return values are not
enforced, and runtime failure remains possible. The [REST generator](rest.md) consumes this readiness report. The historical
[generation workflow](apizr.md) remains independent.

For example, an async function with integer inputs can be ready. A decorator or
later reassignment makes its binding conditional. A generator needs a streaming
adapter and is unsupported. Missing annotations are explicitly unconstrained;
arbitrary application classes and forward references remain uncertain.

## Structured model inputs with TypedDict

Describe a model payload with an ordinary Python `TypedDict`. Your prediction or
calculation function can stay independent of a web framework:

<!-- typed-dict:example -->
```python
from typing import TypedDict, Required, NotRequired


class Features(TypedDict):
    age: int
    score: float


class PredictionInput(TypedDict, total=False):
    customer_id: Required[str]
    features: Required[Features]
    note: NotRequired[str]


def predict(payload: PredictionInput) -> float:
    return payload["features"]["age"] * payload["features"]["score"]
```

Save this as `prediction.py`. Inspect once and generate either interface:

<!-- typed-dict:commands -->
```sh
apizr inspect prediction.py --format json
apizr generate rest prediction.py --output-dir .output/typed-rest
apizr generate mcp prediction.py --output-dir .output/typed-mcp
```

Both interfaces accept
`{"payload":{"customer_id":"c","features":{"age":2,"score":3}}}` and return
`6.0`. The function receives plain Python dictionaries. Missing required fields,
wrong field types and extra fields are rejected at every object level. REST
returns HTTP 422; MCP returns a tool error. Optional fields are omitted rather
than filled with defaults. A return annotation describes the result; it does not
enforce its runtime type.

Supported declarations are module-level class forms using an earlier,
unambiguous `from typing import TypedDict` or `import typing` import (including
aliases). Fields use the shared JSON type vocabulary and may refer to an earlier
supported `TypedDict` in the same module. `total=True` is the default;
`total=False`, `Required[T]` and `NotRequired[T]` determine field presence.
Qualified and aliased stdlib wrappers work too. Explicit `Any` and bare
containers retain their existing unconstrained JSON semantics.
Private class field names follow Python's name mangling: `__value` in `Input`
becomes the JSON key `_Input__value`; prefer ordinary public field names for API
payloads.

The class body may contain a docstring, annotated fields and `pass`. Inheritance,
functional declarations, `typing_extensions`, quoted or recursive/forward
references, generic TypedDicts, annotation calls, field values, methods,
decorators, metaclasses and nonliteral `total` are unsupported. Nesting is bounded
to 32 levels and 4096 expanded type nodes. Duplicate fields and rebound or mutated
typing names are refused. Ordinary classes, dataclasses, Pydantic models and
framework response types do not acquire this exemption. `APIZR-READY-019` and
`readiness.structured_types[].problem` explain an unsupported declaration;
unsafe class initialization still retains `APIZR-READY-004`.

The retained `readiness.structured_types` evidence records the logical name,
source span and typed fields, bound to the inspected source digest. It contains
shape only, without captured values. Analysis never imports or constructs the
declared class.

## Machine output and identity

```sh
apizr inspect example.py --format json
apizr inspect example.py --ir
apizr inspect examples/pricing.ipynb --module-name project.pricing --format json
```

JSON mode emits an `apizr.inspection/v1` envelope containing `capability_ir`,
`ir_digest`, `readiness` and `readiness_digest`. `--ir` emits only the canonical
Capability IR bytes. These selectors are mutually exclusive; neither writes files
unless you redirect stdout.

The logical module defaults to the filename stem. Use `--module-name` for a stable
identity or filenames that are not valid module names. Moving a file while keeping
the same bytes and logical identity preserves machine output. Renaming it without
an override changes identity. Notebook input is exported statically; magics and
shell commands are rejected, and notebook outputs are never executed.

Exit codes are identical for text, JSON and IR output:

- `0`: inspection completed with only ready/conditional assessments (or no capabilities).
- `1`: inspection completed with unsupported/ambiguous assessments or IR errors.
- `2`: operational/input error, including invalid syntax or unsupported file type.

A zero exit code does not mean every capability is eligible or safe to run.
Inspection does not import the target, evaluate decorators/defaults/annotations,
access the network or launch subprocesses. Starting a generated application does
execute its source module and requires trusted input.

See [Static readiness v1](../../architecture/capability-readiness-v1.md) for the
precise bounded policy, reason codes, typed Python API and digest contracts.
