# Integrated journey qualification (#325)

Local qualification on 2026-10-16 passes on native macOS ARM64 with CPython
3.11.14 and 3.15.0, ipykernel 7.4.0 and VS Code 1.140.0. Both installations use
the exact same retained core wheel and VSIX from source `0539a48a`; their build
records and SHA-256 identities are retained here. Production wheel bytes are
unchanged by this qualification-only development work. Package metadata remains
0.4.5 and the unpublished VSIX 0.4.6 pending the coordinated #326 version change.

Each full qualification includes the ordinary uninstrumented notebook journey,
real REST/MCP clients and retained-wheel reproduction, then an integrated SDK
journey against the same installed engine:

- A real Jupyter kernel trains two fraud-detection cohort variants and executes
  a deliberately failing cell. Three v2 Runs retain their actual statuses,
  frontend cell IDs and execution counts. The executed notebook is retained.
- CLI list/show/diff and a clean-profile, installed VSIX return the same canonical
  three records and comparison. The VSIX is uninstalled from that private profile
  after the proof. SDK sessions explicitly name the Python training source;
  unknown executable evidence from unsaved notebook text is not fabricated.
- The second successful Run supplies its exact retained model for real REST and
  MCP predictions. Modified model bytes refuse with `run_artifact_changed`.
- Provider selection can disable the built-in provider. All three records also
  remain readable when importing its implementation is explicitly forbidden.
- Two positive controls exercise the serving observer's `train` and scikit-learn
  `fit` refusals. Both real serving processes are observed, with zero training
  calls. The training marker's bytes and modification time remain unchanged.
- Both transports return probability `0.8127568160788873`; invalid TypedDict
  requests are refused. Independent replay remains byte-identical and works
  without the original projects, Apizr or pandas in the serving environment.

The ordinary and integrated phases take approximately 35 and 36 seconds on
Python 3.11, and 36 and 40 seconds on Python 3.15, excluding preparation and
the separate retained-wheel reproduction. These are local samples, not a
cross-platform latency guarantee. Four negative preflights reject mismatched
VSIX source commits, dirty sources, fixture builds and archive digests before
creating an installation environment. The focused suite passes 213 tests;
Pyright, both architecture gates and strict documentation/128-page HTML checks
pass. Canonical record digests were independently validated after retention.

Host-specific temporary paths are replaced with descriptive placeholders in
review metadata. Scientific records, IDs, values and digests are unchanged.
Executed notebooks are frozen as `integrated-executed.ipynb.json` data: changing
cell formatting after execution would invalidate the retained source digests.
CI retains the original `.ipynb` files for direct opening in Jupyter.
Bundle byte inventories are retained; installable wheels, models and full bundles
are CI artifacts rather than committed binary copies.

CI runs the kernel/CLI/REST/MCP path on all eight existing candidate targets:
Linux CPython 3.11–3.15 and macOS 3.11/3.14/3.15. The existing VS Code job adds
the integrated path with the same coordinated core candidate and its built VSIX.
`release-target-<os>-<python>` and `vscode-qualification` retain JSON results,
executed notebooks, cell sources, logs and generated bundles. Matrix completion
and uploaded artifacts remain required before closing #325. No publication is
performed or authorized by these proofs.

The preceding Homebrew host correction is also verified locally by real
installation, `brew test`, plugin invocation/sync/update/uninstall and remotely by
[job 116981286509](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/38903411947/job/116981286509).
The disposable prototype formula and tap were removed; the user's installed
Apizr was preserved.
