# Analyze a public Git repository

For prerequisites and package availability, see [Install Apizr](../getting-started/install.md).

Readiness and exposure can acquire a public **HTTPS** Git repository directly.
[Private repositories through an explicit SSH agent](git-ssh.md) use the same snapshot API.
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

cat > operator.json <<'JSON'
{
  "schema": "apizr.operator-policy/v1",
  "grants": [
    {
      "adapter": "git",
      "operation": "fetch",
      "permissions": [
        "git.fetch"
      ],
      "target": {
        "transport": "https",
        "repository": "https://github.com/Alien6-Studio/outerspace-apizr.git",
        "reference": "4898669e4990a6d090637436b5884d4d2c2dd41c",
        "subdir": "examples/project-config/src",
        "ca_file": null,
        "ssh_agent_socket": null,
        "ssh_known_hosts": null
      }
    },
    {
      "adapter": "repository",
      "operation": "analyze",
      "target": {
        "kind": "git",
        "repository": "https://github.com/Alien6-Studio/outerspace-apizr.git",
        "reference": "4898669e4990a6d090637436b5884d4d2c2dd41c",
        "subdir": "examples/project-config/src"
      },
      "permissions": [
        "source.analyze"
      ]
    }
  ]
}
JSON

apizr readiness --git "$REPOSITORY" --ref "$REF" --subdir "$SUBDIR" \
  --operator-policy operator.json --policy readiness.json --report
apizr expose plan --git "$REPOSITORY" --ref "$REF" --subdir "$SUBDIR" \
  --operator-policy operator.json --policy exposure.json --readiness-policy readiness.json --plan
apizr expose build rest --git "$REPOSITORY" --ref "$REF" --subdir "$SUBDIR" \
  --operator-policy operator.json --policy exposure.json --readiness-policy readiness.json --output-dir build/rest
apizr expose build mcp --git "$REPOSITORY" --ref "$REF" --subdir "$SUBDIR" \
  --operator-policy operator.json --policy exposure.json --readiness-policy readiness.json --output-dir build/mcp
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
Local development commands also require an explicit `source.analyze` grant.
See [local analysis authorization](operator-policy.md#authorize-repository-analysis).

## Python API

Save this as `snapshot.py` alongside all three policy files above, then run
`python snapshot.py "$REPOSITORY" "$REF" "$SUBDIR"`. Use fresh output directories.

```python
import sys
from pathlib import Path

from apizr.compiler import prepare_exposure, render_bundle
from apizr.exposure import ExposurePolicy
from apizr.git_source import acquire_snapshot
from apizr.operator_policy import load_operator_policy
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_readiness import RepositoryReadinessPolicy

repository, reference, subdir = sys.argv[1:]
exposure = ExposurePolicy.model_validate_json(Path("exposure.json").read_bytes())
readiness = RepositoryReadinessPolicy.model_validate_json(
    Path("readiness.json").read_bytes()
)
operator = load_operator_policy(Path("operator.json"))
with acquire_snapshot(
    repository,
    reference,
    subdir=subdir,
    operator_policy=operator,
) as snapshot:
    print(f"Git snapshot: commit {snapshot.commit}", file=sys.stderr)
    prepared = prepare_exposure(
        snapshot, operator_policy=operator, policy=exposure, readiness_policy=readiness
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

Operator admission raises `AuthorizationDenied` with an `apizr.operator-decision/v1`
result. Without a matching `git.fetch` grant, no Git process, network, trust-file
read or workspace creation occurs. See [exact source grants and path matching](operator-policy.md#authorize-a-git-source).

After admission, acquisition raises `GitSourceError` with fixed codes such as `git_not_found`,
`git_invalid_url`, `git_ref_not_found`, `git_ambiguous_ref`, `git_timeout`,
`git_cancelled`, `git_output_limit`, `git_acquisition_limit` and
`git_snapshot_limit`. CLI acquisition errors return 2; Ctrl-C returns 130 after
cleanup. Raw Git output and URLs
are not echoed in errors. Compiler policy refusals retain their existing codes.

## Boundaries and limits

Git runs without a shell, with a fresh environment, private HOME, empty template,
disabled hooks, credentials, inherited configuration, URL rewriting, proxies,
automatic maintenance and submodule recursion. Only the explicitly selected
HTTPS or SSH transport is enabled.
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

**`subdir` is not a confidentiality barrier:** the repository is acquired and
exported before this directory is selected. A grant does not limit transferred
objects to that subtree. A branch grant authorizes a name resolved at invocation,
not an immutable content identity in advance. Authorization does not replace TLS
or server permissions and does not authorize subsequent analysis as an operator
category; that category remains to be implemented.

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

There is no HTTPS authentication, persistent cache, remote policy loading,
submodule/LFS acquisition, or remote publication in this iteration. Rendering
REST/MCP bundles does not start either server or execute their source code.

## Reproducible installed-wheel proof

Maintainers can run `uv run python scripts/smoke_git_source.py dist/outerspace_apizr-*.whl`.
It creates a disposable minimal wheel installation outside the checkout and a
real smart-HTTPS Git server with an explicitly trusted localhost certificate.
It first traps effects during CLI/API refusals without a policy, then supplies an
explicit fixture-owned grant. It compares all four authorized commands to local sources and executes the Python example
above after deleting the snapshot. No optional packages or plugins are loaded.
The normal installation CI runs this proof for Python 3.11 and 3.14.

Git references: [environment isolation](https://git-scm.com/docs/git),
[shallow fetch](https://git-scm.com/docs/git-fetch), and
[literal object export](https://git-scm.com/docs/git-cat-file).

Analysis takes the live `snapshot`, not `snapshot.root` with a declared origin.
Its context owns the source and resolved commit; after it closes, new analysis
is refused while `PreparedExposure` remains usable. The combined CLI checks both
grants before retrieval. In Python, acquisition and analysis check their own grants.
