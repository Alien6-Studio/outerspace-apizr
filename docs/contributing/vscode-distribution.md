# Build and qualify the VS Code extension

The extension is developed in the dedicated
[`outerspace-apizr-vscode` repository](https://github.com/Alien6-Studio/outerspace-apizr-vscode),
under GPL-3.0-or-later, with its own fast client CI. The engine repository retains
only a generated integration snapshot at `editors/vscode/`. Its runtime npm
dependency count is zero. The four locked build/type-declaration packages are
checked against exact versions, SRI and licence/notice hashes in
`policy/vscode-dependencies.json`; the complete npm audit is blocking without
dependency exclusions. `policy/vscode-distribution.json` pins Node, TypeScript
and the CI VS Code binary and SHA-256.

Develop the client in its own repository. To update the engine's integration
snapshot, check out a clean, exact client commit and run:

```sh
python -m scripts.qualification.packaging.vscode_source --source /path/to/outerspace-apizr-vscode --commit FULL_COMMIT_SHA
```

`policy/vscode-source.json` records the dedicated repository, commit and every
source-file hash. Candidate builds refuse a changed or forked snapshot. This
retains the complete engine/client qualification without coupling ordinary client
development to the engine's full test suite.

```sh
npm ci --prefix editors/vscode --ignore-scripts --no-audit --no-fund
npm test --prefix editors/vscode
npm audit --prefix editors/vscode --include=prod --include=dev --include=optional --include=peer --audit-level=low
python -m scripts.qualification.packaging.vscode_distribution --output /absolute/vscode-dist
```

A retained build requires clean source. `--allow-dirty` is available only for
local development and is recorded explicitly in evidence. The VSIX contains the
extension manifest, own TypeScript source, compiled JavaScript, lock/configuration,
README, pinned CLI descriptor and repository licence. It embeds no engine, `node_modules`, credentials,
project files or experiment store. Sorted stored ZIP entries, fixed timestamps and
modes make repeated builds byte-identical; the build record retains each file's
SHA-256, archive SHA-256, source commit and tool versions.

The `distributions` CI job builds the VSIX alongside the eight Python archives.
Its v2 candidate manifest retains the VSIX hash, complete ZIP inventory, source
commit, reproducibility proof and dependency licence report. The `vscode` job
consumes that same candidate VSIX and engine wheel on development and protected
master. It installs the engine outside the checkout, installs the VSIX into
clean profiles and exercises real inspection, notebook navigation, saved/dirty and
stale results, mixed CLI/SDK/Jupyter history, canonical show/diff, publication
notifications, telemetry opt-out and incompatible-engine refusal. A synthetic
0.4.5 VSIX containing the same reviewed extension code qualifies the update path;
there is no previously published extension implied by that fixture. Uninstall is
checked for extension-owned storage. VS Code retains user-owned settings according
to its normal behaviour. This manual-engine qualification creates no persistent
application storage. Managed installation keeps the CLI and its completion marker
in extension storage; VS Code may retain that storage on uninstall. Project
environments, notebook kernels and local experiment history remain user-owned.

The separate remote proof creates an SSH server in a disposable Docker container,
binds its random port to loopback only and opens the real Remote SSH workspace
extension host. It uses the candidate wheel, hash-locked notebook dependencies,
the same VSIX and the same canonical journey assertions. The repository mount is
read-only; only the temporary proof directory is writable. The extension is
extracted from the qualified VSIX into the disposable server, alongside a distinct
qualification driver. Native installation/update/uninstall remains the proof above.

```sh
python -m scripts.qualification.interfaces.vscode_ssh_proof \
  --wheel /absolute/candidate/outerspace_apizr-0.4.6-py3-none-any.whl \
  --requirements /absolute/engine.lock --vsix /absolute/apizr-0.4.6.vsix \
  --code /absolute/code --output /absolute/fresh-ssh-proof
```

The core wheel and VSIX both declare 0.4.6; retain their exact hashes and source commit.
Use the hash-bearing `uv export --locked --no-default-groups --group
jupyter-qualification --extra notebook --no-emit-project` output as `engine.lock`.
`policy/vscode-distribution.json` pins the Remote SSH tool version and container
base digest. The proof records actual extension versions and artifact hashes,
requires `remoteName == ssh-remote` and an engine outside the checkout, and removes
its desktop process group, container, image tag and client private key afterwards.
Retained qualification requires a clean checkout; `--allow-dirty` is reserved for
explicit local development and is recorded with the qualifier's source hash.
Retain `remote-proof.json`, synthetic fixture/results and top-level proof logs.
Do not publish the raw VS Code profile: its transport logs contain session tokens.
Dev Containers and other remote transports remain unqualified.

The existing required `build` and `dependencies` checks also require this job for
product changes. Web-only routing skips it and still builds documentation. The
existing `codeql` context retains Python and JavaScript/TypeScript SARIF; GitHub's
default Python/Actions alerts remain enabled without duplicate SARIF uploads.

## Publication is a separate authorized operation

The dedicated repository owns extension development and packaging. Its current
`0.4.6` branch is prepared for maintainer review; creating that repository does
not authorize Marketplace/Open VSX publication or a release of the Python engine.

`alien6-studio.apizr` is the **proposed development identity** in `package.json`,
not a claim that a Marketplace/Open VSX publisher has been reserved or verified.
Before any publication, a maintainer must separately authorize the release, verify
publisher ownership on each registry, approve the exact clean-source VSIX/hash and
complete the remaining milestone qualification. Registry credentials belong
outside the repository and CI artifacts.

Marketplace and Open VSX can use the same manifest/VSIX; their publisher setup,
authentication and publication are independent decisions. No `vsce publish`,
`ovsx publish`, tag-triggered publication or registry credential is added here.
Python release versions, tags and publication workflows remain separate.
The reviewed VSIX is included in the common release attachments and protected
CI provenance; this preparation does not enable registry publication.
