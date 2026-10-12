# Fix a refused function

Use the reported reason to make a supported function eligible, then repeat the
same selection and verify its actual response. Do not turn off a protection to
make a request appear successful.

## Before you begin

Keep the source, selection and diagnostic from the failing command. Confirm
`apizr --version` and the interpreter in use. `apizr inspect` reads source without
executing it; repository commands additionally need explicit analysis authority.

| Symptom | Check | Correction | Verify |
| --- | --- | --- | --- |
| `operator_policy_required` | Was the exact local root granted `source.analyze`? | Create/review that bounded operator grant | Repeat the same command with `--operator-policy` |
| Conditional binding | Decorator, reassignment or required import in the diagnostic | Provide a stable module-level function and uniquely resolved helper | Inspect, then plan the same ID |
| Unsupported input | Callable, unresolved class or unsupported TypedDict form | Use a supported JSON shape or ordinary stdlib TypedDict | Send valid and invalid payloads to both transports |
| Unsupported generator | Function contains `yield` | Define a separate finite JSON calculation if that matches your use case | Inspect and explicitly select that function |
| Missing library during Run | Which interpreter runs `apizr`? | Install the workload requirements in that environment | Repeat the trusted Run and inspect its status |
| `run_source_changed` / changed artifact | Source/model no longer matches chosen Run | Restore the exact reviewed bytes or record a new legitimate Run | Expose from the matching successful Run |
| Output already exists | Bundle directory contains files | Choose a new output directory | Build completes and previous bundle stays available |

## Distinguish shape errors from business errors

The quote example's nested input rejects an extra field or string quantity before
invocation: REST responds 422 and MCP returns a tool error. A valid request asking
for unavailable stock reaches the calculation and returns
`{"ok": false, "reason": "insufficient_stock"}`. These are different problems.

## Follow the dependency path

An incomplete notebook unrelated to a selected prediction is different from an
unsafe initializer in its required feature helper. The [research scenario](../examples/research-serving.md)
adds a real defect, observes refusal, restores the legitimate helper and verifies
REST/MCP again. `--allow-conditional` cannot waive missing required evidence or
unsupported input contracts.

For persistent runtime/configuration errors, continue with
[operations troubleshooting](../operations-guide/troubleshooting.md).
Exact readiness codes and bounds remain in
[static readiness](../architecture/capability-readiness-v1.md).
