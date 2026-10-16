# Build and qualify the VS Code extension

The extension stays in `editors/vscode/`, under GPL-3.0-or-later. Its runtime npm
dependency count is zero. The four locked build/type-declaration packages are
checked against exact versions, SRI and licence/notice hashes in
`policy/vscode-dependencies.json`; the complete npm audit is blocking without
dependency exclusions. `policy/vscode-distribution.json` pins Node, TypeScript
and the CI VS Code binary and SHA-256.

```sh
npm ci --prefix editors/vscode --ignore-scripts --no-audit --no-fund
npm test --prefix editors/vscode
npm audit --prefix editors/vscode --include=prod --include=dev --include=optional --include=peer --audit-level=low
python -m scripts.qualification.packaging.vscode_distribution --output /absolute/vscode-dist
```

A retained build requires clean source. `--allow-dirty` is available only for
local development and is recorded explicitly in evidence. The VSIX contains the
extension manifest, own TypeScript source, compiled JavaScript, lock/configuration,
README and repository licence. It embeds no engine, `node_modules`, credentials,
project files or experiment store. Sorted stored ZIP entries, fixed timestamps and
modes make repeated builds byte-identical; the build record retains each file's
SHA-256, archive SHA-256, source commit and tool versions.

The `vscode` CI job consumes the same coordinated candidate wheel as other product
qualification. It installs the engine outside the checkout, installs the VSIX into
clean profiles and exercises real inspection, notebook navigation, saved/dirty and
stale results, mixed CLI/SDK/Jupyter history, canonical show/diff, publication
notifications, telemetry opt-out and incompatible-engine refusal. A synthetic
0.4.5 VSIX containing the same reviewed extension code qualifies the update path;
there is no previously published extension implied by that fixture. Uninstall is
checked for extension-owned storage. VS Code retains user-owned settings according
to its normal behaviour; the extension creates no persistent application storage.
Its local history remains owned by the engine/user and is never removed on uninstall.

The existing required `build` and `dependencies` checks also require this job for
product changes. Web-only routing skips it and still builds documentation. The
existing `codeql` context retains Python and JavaScript/TypeScript SARIF; GitHub's
default Python/Actions alerts remain enabled without duplicate SARIF uploads.

## Publication is a separate authorized operation

`alien6-studio.apizr` is the **proposed development identity** in `package.json`,
not a claim that a Marketplace/Open VSX publisher has been reserved or verified.
Before any publication, a maintainer must separately authorize the release, verify
publisher ownership on each registry, approve the exact clean-source VSIX/hash and
complete the remaining milestone qualification, including the remote-host case in
#312. Registry credentials belong outside the repository and CI artifacts.

Marketplace and Open VSX can use the same manifest/VSIX; their publisher setup,
authentication and publication are independent decisions. No `vsce publish`,
`ovsx publish`, tag-triggered publication or registry credential is added here.
Python release versions, tags and publication workflows remain separate.
