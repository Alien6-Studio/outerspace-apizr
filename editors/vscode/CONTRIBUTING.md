# Contributing

Use branch `0.4.6`, Node 22.22.2 and Python 3.11 or newer.

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm audit --include=prod --include=dev --include=optional --include=peer --audit-level=low
npm run package
```

`dist/` contains a reproducible, source-including VSIX and build/licence evidence.
A retained build requires clean Git source. `--allow-dirty` is only for local
iteration. Install it with `code --install-extension dist/apizr-0.4.6.vsix --force`.

The fast CI qualifies the client independently. The engine repository runs native
VS Code/SSH and CLI/SDK/Jupyter integration against the pinned client snapshot and
candidate engine. No workflow in this repository publishes an extension or engine.

Sign commits with `git commit -s`. Report product bugs in this repository; include
VS Code/engine versions and a minimal sanitized example, without private Run data.
