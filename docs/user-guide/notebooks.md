# Prepare notebooks, dependencies and files

Turn an ordinary notebook function into a callable service without relying on
its interactive kernel state. The result must run from the generated bundle and
its declared runtime inputs.

## Before you begin

Use the [notebook installation path](../getting-started/install.md#data-scientist).
Inspection needs the notebook extra, not pandas or scikit-learn. A Run needs the
scientific packages in the interpreter running Apizr. A service needs its own
transport and selected application dependencies.

## Inspect an ordinary notebook first

```sh
apizr experiment inspect fraud_detection.ipynb
```

Use the [fraud files](../examples/compare-fraud.md) for this command. Stored cell
outputs and execution counts are not current results. Supported notebooks are
nbformat 4 with ordinary Python cells. Magics and shell cells are refused; convert
these operations into explicit preparation commands and inspect again.

## Keep training out of service startup

Define the prediction function at module level. Put training under the exact
`if __name__ == "__main__":` guard, without an `else`, and do not rebind `__name__`.
The fraud notebook follows this pattern. A saved model is loaded by trusted
prediction code on demand. Static analysis does not deserialize it.

Cells must work in document order from a clean process. A value created only by
a previous interactive session is unavailable to Apizr's fresh worker. Verify
with an explicit Run in the workload environment before sharing that result.

## Keep the service's files explicit

In a project file, `[application] resources` declares individual regular files,
while `dependencies` declares exact distribution pins. Paths retain their layout
under `source/`. Use paths derived from `__file__` so starting from another
working directory does not accidentally load a different file.

For a Run-based service, select an output by recorded name (`--artifact model`),
not an arbitrary replacement pathname. The current bytes must match that Run.
Resources are limited to 16 MiB each and 32 MiB combined, with at most 128 files.
This direct-service workflow is not a model registry or an arbitrary filesystem
packager. See [application inputs](../getting-started/user-guide/project.md#application-dependencies-and-resources-041-development).

## Prepare dependencies at the correct time

Inspection does not install dependencies. Download scientific wheels only when
preparing to run the notebook. Retain the wheels used by the chosen Run for
`--dependency-wheelhouse`; provider membership remains conditional evidence.
The [prediction scenario](../examples/share-prediction.md) selects joblib and
scikit-learn, with pandas remaining a training dependency.

Install both the generated `requirements.txt` and, when present,
`application-requirements.txt` in the service environment. Application pins alone
do not make an unsupported function eligible. Check a real request after startup,
then follow [safe regeneration](../developer-guide/regeneration.md) for updates.
