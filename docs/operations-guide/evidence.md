# Preserve configuration and evidence

Retain the bytes and identities needed to diagnose or review a service while
keeping local machine authority and sensitive observations controlled.

## Before you begin

Identify the explicit project file, operator grants, plugin store, bundle and
experiment store used by your commands. Do not assume a global history or a shared
transaction snapshot. Local records can include business-sensitive literals,
references, metrics and chosen parameters even when arbitrary logs are discarded.

| Location | What it holds | Retention consideration |
| --- | --- | --- |
| `apizr.toml` and selected policy files | Project intent, exact pins/resources and selection | Version with the application after review |
| `.apizr/operator.json` from init | Machine-local exact-root grant | Ignored by Git; review rights and root on another host |
| Explicit plugin store | Installed environments/inventory/activations | Retain locks, wheel identities and chosen versions |
| `ROOT/.apizr/experiments/v1` | Canonical Plans/Runs and hashes | Local evidence, not model bytes or remote tracking |
| Generated bundle directory | Contracts, source and selected resources | Source privacy matters even for private API helpers |
| Chosen delivery output | Build/push/proof/observations | Keep exact bytes and independent trusted identities |
| External credential/key paths | Registry auth and private signing key | Keep outside projects/bundles; never print into evidence |

## Inspect what will be shared

Plans store selected environment variable names, not their values. Deliberately
selected metrics/parameters can still contain sensitive data. Inspector output
contains source literals and references. Bundles include all inspected Python
sources and explicitly selected resources; API privacy is not source secrecy.
Public exported documents can contain docstrings/declared expressions even when
source files and keys are omitted. Review them before upload.

## Make a quiescent local backup

Stop or finish the writers you own before copying local history. Copy the entire
`plans/` and `runs/` tree together to controlled storage, preserving permissions
and exact file bytes. Do not edit JSON, rename hashes or copy only filtered Runs.
Apizr provides no guaranteed live backup, shared locking or multi-user tracker.

Verify a restored copy with:

```sh
apizr experiment list --store ../restored-history --format json
```

Use the path you actually copied. This verifies canonical identities and Run/Plan
binding, including records outside the display limit. It does not verify model
bytes, which the store does not retain. Keep selected model resources separately
with their recorded size/hash and storage access policy.

## Handle corruption without rewriting history

Store reads refuse changed hashes, noncanonical bytes, missing components and
symlinks. Preserve the failing tree for diagnosis. Restore a verified backup into
a different location rather than deleting a diagnostic file until queries pass.
A crash can leave orphan Plans or staged entries; there is no automatic repair.
Use the [store contract](../getting-started/user-guide/experiment-runs.md#local-immutable-store)
for limits and publication details.

Apply retention through your own storage procedures. Apizr does not provide
central cleanup, synchronization or a model-registry stage transition.
