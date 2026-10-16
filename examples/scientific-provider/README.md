# Literal accuracy provider

This dependency-free, separately packaged example implements `scientific.describe`
and `scientific.recognize` over `apizr.extension/v1`. It recognizes a deliberately
narrow literal `sklearn.metrics.accuracy_score` call without importing sklearn or
executing inspected source. It reports a static metric signal, never its value.
The producer identity is `example.literal-accuracy` version `1`; the wheel is
`apizr-literal-accuracy` version `0.0.0`.

Build with `uv build --wheel examples/scientific-provider`, then install and
activate the wheel through `apizr plugins install` and `apizr plugins activate`
using the ordinary local extension workflow. See
`docs/reference/scientific-providers.md` for the explicit selection JSON.
Describing or invoking this extension executes its trusted code in the extension
environment. It never writes to the evidence store.

`scripts/qualification/experiments/scientific_contract_proof.py`, called by the
installed-wheel CI smoke, builds this package outside the checkout, installs and
activates it in a separate environment, validates recognition, disables and removes
it, then reads and compares the retained Runs with no producer available. It also
checks that the core environment's installed distribution inventory is unchanged.
