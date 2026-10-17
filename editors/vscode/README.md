# Apizr for VS Code

Inspect Python files and notebooks, browse experiment history and compare Runs.

Requires **VS Code 1.140+** and an installed **Apizr 0.4.6** engine.

## Get started

1. Open a trusted project containing `apizr.toml`.
2. Run **Apizr: Select engine**, then **Apizr: Check engine** from the command palette.
3. Set `apizr.operatorPolicy` to your policy file, granting `source.analyze` and
   `history.read` for the project and experiment store.

## Use

- **Apizr: Inspect with Apizr** — inspect a saved `.py` or `.ipynb` file.
- **Apizr: Refresh runs** — browse history in the **Apizr Runs** view.
- **Apizr: Compare two Runs** — compare selected records.

Inspection does not execute your code. Telemetry is off by default.

[Setup and settings](https://github.com/Alien6-Studio/outerspace-apizr/blob/0.4.6/docs/reference/vscode.md)
