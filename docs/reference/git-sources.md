# Analyze a public Git repository

Readiness and exposure can acquire a public **HTTPS** Git repository directly.
Install Git separately; this adapter is included in the minimal Apizr core and
does not install or invoke plugins. Python 3.11–3.14 on macOS/Linux is supported.

## One explicit revision

Run these commands from an empty local working directory. The policies are local
files you control; Apizr does not load policies or `apizr.toml` from the remote.
This example selects the small calculator source already present in Apizr's
repository at the specified immutable commit:

```sh
REPOSITORY=https://github.com/Alien6-Studio/outerspace-apizr.git
REF=4898669e4990a6d090637436b5884d4d2c2dd41c
SUBDIR=examples/project-config/src

cat > readiness.json <<'JSON'
{"execution":{"modes":["direct"]}}
JSON
cat > exposure.json <<'JSON'
{"selection":{"include":["python:calculator:add"]},"interfaces":["rest","mcp"],"execution":{"allowed":["direct"]}}
JSON

apizr readiness --git "$REPOSITORY" --ref "$REF" --subdir "$SUBDIR" \
  --policy readiness.json --report
apizr expose plan --git "$REPOSITORY" --ref "$REF" --subdir "$SUBDIR" \
  --policy exposure.json --readiness-policy readiness.json --plan
apizr expose build rest --git "$REPOSITORY" --ref "$REF" --subdir "$SUBDIR" \
  --policy exposure.json --readiness-policy readiness.json --output-dir build/rest
apizr expose build mcp --git "$REPOSITORY" --ref "$REF" --subdir "$SUBDIR" \
  --policy exposure.json --readiness-policy readiness.json --output-dir build/mcp
```

`--ref` is mandatory: a branch, tag (including annotated tags), or full commit
object ID. A short name shared by a branch and tag is refused even if both point
to the same commit; qualify it as `refs/heads/name` or `refs/tags/name`.
No default branch or abbreviated-commit fallback is used. The server must allow
fetching the resolved object; if it disappears or access is refused, acquisition
fails rather than silently selecting a newer revision.

The resolved commit is printed to **stderr**, leaving canonical JSON on stdout.
`--subdir` selects a directory inside the snapshot. `--source-root` retains its
scanner meaning, relative to that selected directory. `--git` cannot be combined
with a positional local root or `--project`; `--ref` and `--subdir` require `--git`.
Commands without `--git` retain their existing behavior and exit codes.

## Python API

Save this as `snapshot.py` alongside the two policy files above, then run
`python snapshot.py "$REPOSITORY" "$REF" "$SUBDIR"`. Use fresh output directories.

```python
import sys
from pathlib import Path

from apizr.compiler import prepare_exposure, render_bundle
from apizr.exposure import ExposurePolicy
from apizr.git_source import acquire_snapshot
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_readiness import RepositoryReadinessPolicy

repository, reference, subdir = sys.argv[1:]
exposure = ExposurePolicy.model_validate_json(Path("exposure.json").read_bytes())
readiness = RepositoryReadinessPolicy.model_validate_json(
    Path("readiness.json").read_bytes()
)
with acquire_snapshot(repository, reference, subdir=subdir) as snapshot:
    print(f"Git snapshot: commit {snapshot.commit}", file=sys.stderr)
    prepared = prepare_exposure(
        snapshot.root, policy=exposure, readiness_policy=readiness
    )

# The temporary snapshot is already deleted; the compiler retained its sources.
for interface in ("rest", "mcp"):
    bundle = render_bundle(prepared, interface=interface)
    write_bundle(Path("python-" + interface), bundle)
```

`GitSnapshot` identifies `repository`, `requested_ref`, resolved `commit`, selected
`subdir` and ephemeral `root`. The context manager cleans up on success, refusal
and interruption. It does not catch or reclassify errors raised by your analysis.
`AcquisitionLimits` configures the bounds below, and an optional `threading.Event`
passed as `cancel` cancels acquisition. `ca_file=Path(...)` can explicitly trust a
CA in Python tests; certificate and hostname verification remain enabled.

Acquisition raises `GitSourceError` with fixed codes such as `git_not_found`,
`git_invalid_url`, `git_ref_not_found`, `git_ambiguous_ref`, `git_timeout`,
`git_cancelled`, `git_output_limit`, `git_acquisition_limit` and
`git_snapshot_limit`. CLI acquisition errors return 2; Ctrl-C returns 130 after
cleanup. Raw Git output and URLs
are not echoed in errors. Compiler policy refusals retain their existing codes.

## Boundaries and limits

Git runs without a shell, with a fresh environment, private HOME, empty template,
disabled hooks, credentials, inherited configuration, URL rewriting, proxies,
automatic maintenance and submodule recursion. Only HTTPS transport is enabled.
TLS verification is mandatory. Embedded credentials, query strings, fragments
and redirects are refused; use the final canonical public repository URL.
The executable found on PATH and its installed Git helpers must be trusted.

There is **no checkout**, source import, dependency installation or execution of
project code. Raw blobs are exported with `cat-file`, without smudge/textconv
filters or archive attributes (`export-ignore`/`export-subst`). All symlinks,
submodule entries and LFS pointers are refused, including outside the selected
subdirectory, so missing content cannot masquerade as a complete analysis.
Paths cannot leave the snapshot; `.git` and acquisition files are never exported.
Source filenames must be UTF-8 and portable relative paths. Case-colliding files
are refused if the host filesystem cannot represent them separately.

Default acquisition bounds (independent of the existing scanner bounds):

| Bound | Default | Enforcement |
| --- | --- | --- |
| Total acquisition time | 120 seconds | One deadline across Git commands and export |
| Git stdout per command | 80 MiB | Bounded while reading; metadata commands additionally capped at 4 MiB |
| Git stderr per command | 64 KiB | Bounded while reading, never included in diagnostics |
| Acquisition disk volume | 128 MiB | Sampled during Git execution and checked after commands/export |
| Snapshot regular files | 10,000 | Checked before writing blobs |
| One snapshot file | 8 MiB | Checked from object metadata before reading blobs |
| Total snapshot file bytes | 64 MiB | Checked before reading/writing blobs |

The disk limit is an **observed-volume limit, not a hard network-byte quota**.
Git can receive/write more bytes between samples; compressed packs can expand
substantially, and a shallow fetch does not guarantee a small transfer. Acquisition
is terminated when a measured bound is exceeded; no result is returned. The
adapter also bounds filesystem-entry inspection. A busy filesystem can delay
observation. This is not a disk/memory sandbox or a defense against a malicious
Git executable: keep Git patched. Normal helper process groups are killed and
the direct child is reaped on errors/interruption; detached descendants and
uninterruptible kernel work cannot be guaranteed terminated. Cleanup failure is
explicit (`git_cleanup_failed`).

There is no SSH, private authentication, persistent cache, remote policy loading,
submodule/LFS acquisition, or remote publication in this iteration. Rendering
REST/MCP bundles does not start either server or execute their source code.

## Reproducible installed-wheel proof

Maintainers can run `uv run python scripts/smoke_git_source.py dist/outerspace_apizr-*.whl`.
It creates a disposable minimal wheel installation outside the checkout and a
real smart-HTTPS Git server with an explicitly trusted localhost certificate.
It compares all four commands to local sources and executes the Python example
above after deleting the snapshot. No optional packages or plugins are loaded.
The normal installation CI runs this proof for Python 3.11 and 3.14.

Git references: [environment isolation](https://git-scm.com/docs/git),
[shallow fetch](https://git-scm.com/docs/git-fetch), and
[literal object export](https://git-scm.com/docs/git-cat-file).
