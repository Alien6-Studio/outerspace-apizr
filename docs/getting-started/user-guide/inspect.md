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

## Read the result

| State | What it means |
| --- | --- |
| `ready` | Enough static contract evidence to describe an ordinary JSON/value interface |
| `conditional` | Binding, initialization, dependencies or input semantics remain uncertain |
| `unsupported` | A contract needs an adapter this policy does not define, such as streaming or Callable inputs |
| `ambiguous` | Static evidence cannot select one coherent callable contract |

`can_generate_interface` is true only for a `ready` IR capability. It is not
permission to execute code. Effects remain unknown, return values are not
enforced, and runtime failure remains possible. No generator consumes this
readiness report yet. The existing [generation workflow](apizr.md) is independent.

For example, an async function with integer inputs can be ready. A decorator or
later reassignment makes its binding conditional. A generator needs a streaming
adapter and is unsupported. Missing annotations are explicitly unconstrained;
arbitrary application classes and forward references remain uncertain.

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
