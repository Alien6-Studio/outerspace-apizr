# Know exactly which local data you used

```python
import pandas as pd

df = pd.read_parquet("data/train.parquet")
```

Apizr can recognize this literal reference from Python syntax. A separate,
explicit fingerprint operation can record `data/train.parquet`, its exact size
and SHA-256, with static content provenance. Neither operation imports pandas
or reads rows into a DataFrame.

SHA-256 evidence identifies bytes. Apizr does not upload, cache, version, restore
or distribute the dataset. It identifies experiment inputs; it does not own them.
Changing training data changes Experiment Plan identity. It does not change the
logical capability ID by itself.

## Use the Python API

This runnable example uses a temporary local file. It performs discovery without
dataset access, then explicitly selects an input, fingerprints it, and constructs
a new frozen Plan. No experiment CLI exists yet.

<!-- executable-input-example -->
```python
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from apizr.experiments import (
    ExecutionIntent,
    ExperimentPlan,
    SourceIdentity,
    discover_inputs,
    fingerprint_inputs,
    parse_input_declaration,
    plan_digest,
    select_inputs,
)

source = b'import pandas as pd\npd.read_csv("data/train.csv")\n'
found = discover_inputs(source, source_reference="train.py")
selection = select_inputs(found, (parse_input_declaration("training=data/train.csv"),))

with TemporaryDirectory() as directory:
    root = Path(directory)
    (root / "data").mkdir()
    (root / "data/train.csv").write_bytes(b"feature,label\n0.25,0\n")
    observed = fingerprint_inputs(root, selection.artifacts)
    assert not observed.diagnostics
    plan = ExperimentPlan(
        subject=SourceIdentity(
            kind="python",
            reference="train.py",
            digest=sha256(source).hexdigest(),
            capability_id="python:train:train",
        ),
        execution=ExecutionIntent(kind="training"),
        inputs=observed.artifacts,
    )
    identity = plan_digest(plan)
    assert plan.inputs[0].origin.value == "declared"
    assert plan.inputs[0].content_origin.value == "static"
```

`InputDeclaration(name="training", reference="data/train.parquet")` and
`fingerprint_input(root, declaration)` also work independently of discovery.
The parser accepts `name=reference`, splitting at the first `=` without trimming.
`--input training=data/train.parquet` is future CLI syntax, not an executable
command delivered here. Invalid parser input raises the bounded error
`explicit_input_invalid`, without echoing paths or credentials.

All producer result objects are frozen, strict typed values. `InputResult` contains
`artifacts` and `diagnostics`; it is not a partial Experiment Plan. Check diagnostics
before deciding which evidence to put in a Plan. Fingerprinting returns new
artifacts; it never mutates an existing Plan. Failed local observations retain the
reference with unknown content and no digest or size. Supplied hash/size claims
are discarded before every observation, including failed or remote observations.

## What the static recognizer understands

| Loader | Canonical format hint |
| --- | --- |
| `pandas.read_csv` | `csv` |
| `pandas.read_parquet` | `parquet` |
| `numpy.load` | `numpy` |
| `joblib.load` | `joblib` |

Only a literal string in the first positional argument is recognized. Additional
loader options are not interpreted. No keyword path forms are supported in v1.
Ordinary imports, `import pandas as pd`, `from pandas import read_csv`, and
`from pandas import read_csv as read` are recognized without importing the library.
Clearly inherited module/function bindings work inside functions, including async
functions. Local unambiguous imports work as well.

Lexical analysis intentionally rejects ambiguous bindings: repeated/rebound or
deleted aliases, star/conditional/relative imports, parameters and other local
shadowing, nested global/nonlocal declarations, and explicit attribute writes.
It does not infer library identity from a variable's spelling. A direct call must
follow its import syntactically. Whole-scope conservatism can discard an earlier
valid read if the alias is later rebound. Class namespaces do not grant authority
to methods or nested comprehension scopes. Generic definitions with PEP 695
type parameters are outside this initial recognizer and are ignored in full.
Unsupported loaders are ignored;
indirect `get_loader()(...)` calls produce `unsupported_input_reference`.

These observations describe syntax, not proof a call executes or a branch is
reachable. Arbitrary Python side effects cannot be modeled statically. No source
import, evaluation, subprocess, environment-variable resolution or network access
occurs. Notebook extraction belongs to the future notebook analysis integration;
its normalized Python can use this same source-only API.

```python
pd.read_parquet(DATA_PATH)
```

Apizr does not guess the value of `DATA_PATH`, even if a constant assignment
appears elsewhere. Variables, indexing, f-strings, computed `Path` expressions,
starred arguments and keyword-only calls retain `dynamic_input_reference`.

A declaration such as `training=data/train.parquet` declares experiment intent;
it does not prove the Python expression evaluates to that path. `select_inputs`
retains the discovery diagnostics while allowing explicitly named inputs into the
selection. Explicit names replace static candidates for the same reference and
keep declared origin. Different explicit names may select identical bytes;
digests do not determine logical input names. Duplicate names are rejected before
any batch reads, never resolved with last-write-wins.

Static names equal the exact local reference or reviewed URI. References longer
than the 128-character name bound produce `input_name_required`; use an explicit
short name. Repeated reads of the same reference collapse. Incompatible loader
hints clear the hint and add `input_format_conflict`. Candidates and diagnostics
are sorted deterministically. Diagnostic locations contain the relative source,
1-based line, 0-based UTF-8 column and recognized loader, without source excerpts.

## Remote references stay unverified

```python
pd.read_parquet("s3://bucket/train.parquet")
```

Apizr can record the reference but does not download remote data merely to
manufacture a content fingerprint. `uri` carries the remote reference; `reference`
remains reserved for local project-relative paths. Their fields are mutually
exclusive. Static and declared remote records retain their reference origin,
`content_origin=unknown`, absent digest/size and `remote_content_unverified`.
No GET, HEAD, cloud SDK, credential lookup or local filesystem traversal occurs.

The deliberately narrow v1 URI syntax supports lowercase `https://`, `s3://` and
`gs://`; an ASCII lowercase alphanumeric authority may contain internal dots and
hyphens separated by alphanumeric runs. Optional nonempty path segments contain
only ASCII letters, digits, `.`, `_`, `~` or `-`; standalone `.` and `..` segments
are rejected. Maximum length is 1024 characters. No trailing/doubled slash,
userinfo, password, port, query, fragment, percent escape, Unicode authority,
control character or `file://` scheme is accepted. This is a conservative evidence
syntax, not a general URL validator. It cannot detect secrets placed in ordinary
path segments; producers must not insert sensitive reference strings.

## Local fingerprint safety and limits

One input represents one regular file under an explicit project root. References
are portable POSIX-style relative paths, maximum 1024 characters. Absolute paths,
`..`, `.`, empty segments, backslashes, drive/colon prefixes, home expansion and
control characters are rejected without normalization. Absolute source literals
produce redacted `nonportable_input_reference` diagnostics.

The producer reuses `workspace.files.directory_fd` for no-follow root traversal
and opens child components relative to directory descriptors. Input-file symlinks
and symlink parents are rejected, even when they point inside the project. Existing
macOS `/tmp` and `/var` system aliases follow the shared root policy. Ordinary
hard links are allowed: identity uses the logical reference and bytes, not inode.
Directories, file sets, devices, FIFOs and sockets are unsupported. Nonblocking,
no-follow opens and descriptor regular-file checks prevent special-file waits and
symlink swaps from granting read authority.

Hashing streams exact file bytes with SHA-256 in chunks of at most **1 MiB**.
`FingerprintPolicy.max_file_bytes` defaults to **1 GiB**, configurable from 1 byte
to a hard maximum **1 TiB** per file. The batch maximum is **256 inputs** (therefore
at most 256 times the selected per-file limit); no directory traversal or implicit
file selection occurs. Source discovery separately admits at most **1 MiB** of
Python, **100,000 AST nodes**, depth **128**, **256 unique candidates** and **512
diagnostics**. Exceeding a discovery budget returns only `input_discovery_limit`,
not a silently partial scan. Invalid Python/source identity produces
`input_source_invalid`.

Before/after `fstat` snapshots compare device, inode, size, nanosecond mtime and
ctime. The final directory-relative path identity and exact bytes-read count must
also agree. Mutation discards the entire digest with `input_changed_during_read`;
exceeding the read budget produces `input_too_large`. This detects observable
mutation; it is not a filesystem snapshot or protection against privileged
adversaries defeating filesystem metadata. Other failures distinguish
`input_missing`, `input_symlink`, `input_not_regular` and `input_unreadable`.
Root traversal errors are sanitized through the same codes; an `ENOTDIR` from a
no-follow root/parent open is reported as `input_not_regular`.

Dataset bytes, absolute roots, inode/device, timestamps and permission bits never
enter evidence or diagnostics. Identical bytes and logical references at different
roots produce identical artifacts and Plan digests. Only the selected file is
read; no neighboring files, sidecars, dataset copies, writes, caches or watch
services are involved.

An explicit selection yields `origin=declared`, while successfully observed local
bytes yield `content_origin=static`. Static selections keep `origin=static` and
also receive `content_origin=static` after hashing. Format hints for declarations
come only from exact lowercase suffixes `.csv`, `.parquet`, `.npy`, `.npz` and
`.joblib`; unknown extensions have no hint. No content sniffing occurs. A canonical
format hint can change Plan identity even when bytes match; it is not proof of
parser behavior.

## Interoperability and contract boundary

DVC, MLflow, W&B and external catalogs can become future evidence adapters. They
are not core dependencies. No dataset store, runtime capture, metric collection,
randomness/environment capture, experiment execution, history or CLI is added.
The minimal core needs no pandas, NumPy, joblib, pyarrow or remote storage SDK.

The additive `InputArtifact` fields preserve old Plan/Run v1 canonical bytes when
absent. See [experiment evidence v1](../architecture/experiment-evidence-v1.md#additive-input-evidence-in-045-development)
for provenance constraints and schema limits. Fingerprinted inputs are reusable
Plan evidence; future Run producers must separately supply runtime observations.
