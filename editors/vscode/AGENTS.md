# Extension development

Work on `0.4.6`. This repository owns the VS Code client. The Apizr engine owns
scientific admission, history validation and comparison through `apizr.editor/v1`.
Do not implement those operations in TypeScript or execute inspected source.

Keep the official Apizr icon, concise user-facing documentation and zero runtime
npm dependencies. Engine installation uses only the bundled pinned descriptor,
requires an explicit action in a trusted native host and never modifies a project
venv. Preserve cancellation, process/output bounds and lossless numeric rendering.

Run `npm test` and the complete dependency audit using the pinned Node version
before committing, then `npm run package` on the clean commit. Keep Marketplace/Open VSX/PyPI, tags,
releases and changes to protected branches behind separate maintainer approval.
The core repository consumes a generated, commit-pinned integration snapshot;
update it with its sync command, never maintain a second client implementation.
