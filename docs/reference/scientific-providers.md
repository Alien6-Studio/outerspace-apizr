# Select scientific providers

The 0.4.6 development engine exposes explicit scientific-provider selection.
The default is `apizr.builtin` version `1`, shipped in the core wheel. Providers
recognize static input reads, metric calls, output candidates and randomness
controls. Recognition does not prove runtime values or reproducibility.

```bash
apizr providers list
apizr providers list --format json
apizr experiment inspect model.py --providers providers.json --format json
apizr experiment run model.py --providers providers.json
```

`providers.json` uses the [selection schema](../specs/apizr-provider-selection-v1.schema.json).
For example, select an already installed, explicitly activated extension for
metrics and retain built-in recognition for the other capabilities:

```json
{
  "schema_version": "apizr.provider-selection/v1",
  "providers": [
    {
      "identity": {"name": "example.literal-accuracy", "version": "1"},
      "capabilities": ["metric_signals"],
      "enabled": true,
      "extension": "apizr-literal-accuracy"
    },
    {"identity": {"name": "apizr.builtin", "version": "1"}}
  ]
}
```

The **first entry claiming a capability owns it**, including when disabled or
unavailable. Later entries own only remaining capabilities. There is no fallback
after failure. Set `enabled` to `false` to disable an entry; use `"providers": []`
to disable all automatic scientific recognition. Explicit declarations and
runtime SDK logging retain their own contracts.

`providers list --selection providers.json --directory STORE` lists the selected
inventory with exact identities, descriptors, capabilities, limits, active entries
and ownership. This is an explicit inventory, not discovery of every installed
package. Disabled or fully shadowed extensions are never invoked, so their
descriptor is unknown. The built-in descriptor is always known. JSON output
follows the [provider report schema](../specs/apizr-scientific-providers-v1.schema.json).

Use `--provider-directory STORE` with `experiment inspect` or `experiment run`
when the selected extension lives in a nondefault extension store. Selection
never installs, activates or imports arbitrary packages. Describing or recognizing
with a selected external provider **executes trusted installed extension code**
through the existing [extension protocol](extension-invocation.md). Process limits
are 10 seconds, a 4 MiB request and 1 MiB stdout; descriptor JSON is limited to
64 KiB. The selection file is limited to 64 KiB, 16 entries and bounded JSON depth.
Provider-declared source, AST and result limits can only lower core ceilings.

## Python API

```python
from apizr.scientific_providers.contracts.selection import ProviderSelection
from apizr.scientific_providers.selection import list_providers
from apizr.experiments.inspection import inspect_experiment

selection = ProviderSelection()  # Explicit built-in selection.
inventory = list_providers(selection)
inspection = inspect_experiment("model.py", providers=selection)
print(inventory.model_dump_json())
```

For a trusted in-process implementation, supply an explicit
`provider_implementations={"name": instance}` mapping to `inspect_experiment` or
`run_experiment`, or `implementations` to `list_providers`. Its descriptor must
match the selected name and version exactly. `apizr.builtin` is reserved. No
entrypoint scanning or global registry is used. Each admitted `SourceView` carries
immutable bounded source facts shared during that inspection; `tree()` always
returns a fresh mutable AST owned by its caller.

## Diagnostics and retained evidence

| Code | Meaning |
| --- | --- |
| `provider_disabled` | Explicitly disabled; selected evidence is unknown. |
| `provider_shadowed` | Earlier entries own every requested capability; not invoked. |
| `provider_unavailable` | Missing implementation or unavailable installed extension/descriptor. |
| `provider_incompatible` | Descriptor is invalid or has a different identity/version. |
| `provider_unsupported` | Descriptor does not support a selected capability. |
| `provider_failed` | Recognition raised or its extension invocation failed. |
| `provider_result_invalid` | Candidate failed source binding or core result admission. |
| `provider_limit` | Source/request/result exceeded an admitted bound. |

Refused evidence stays unknown and raw provider exception text is not exposed.
Provider candidates are revalidated before use; identity, source digest, locations,
capabilities and aggregate result limits remain core authority.

`experiment run` records the provider report in the Plan's immutable
`execution.controls` entry `scientific_providers`. The Run binds that Plan by
digest. `experiment show` and `experiment diff` read the retained report without
loading the producer, including after uninstall. Diff presents provider changes as
context, without claiming they caused an outcome change. Historical records
without a report remain readable and yield unknown provider comparison context.
Standalone inspection without an explicit selection preserves its historical
wire output; an explicit selection adds the provider report.

The separately packaged [literal-accuracy example](https://github.com/Alien6-Studio/outerspace-apizr/tree/0.4.6/examples/scientific-provider)
and installed-wheel qualification demonstrate protocol invocation and reading
history after uninstall. See the [provider contracts](../architecture/scientific-providers-v1.md)
for authoring and admission details.
