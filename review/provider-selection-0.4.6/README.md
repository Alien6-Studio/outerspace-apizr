# Explicit provider selection qualification (#310)

The installed proof runs the built core wheel with `python -I -B` outside the
checkout. The wheel retains the current development metadata version 0.4.5;
coordinated version/publication changes remain separate release work.

`installed-proof.json` records the actual wheel identities and outcome. The
separately packaged, dependency-free `examples/scientific-provider` is copied
outside the checkout, built into a valid wheel, installed into a dedicated plugin
environment, explicitly activated and invoked through `apizr.extension/v1`.
The core environment's installed distribution inventory remains unchanged.

The proof verifies positive literal metric recognition and negative cases
(pre-import calls, replaced aliases, dynamic arguments and namespace mutation),
then captures Runs with enabled and disabled selection. It disables and uninstalls
the extension, checks `provider_unavailable`, and reads/compares the retained
producer versions without a producer installation. Installed-wheel CI executes
this proof through `smoke_wheel`; no additional plugin loader is introduced.

Regression tests independently cover missing, disabled, incompatible, failing,
over-limit and invalid-result providers, explicit precedence with no fallback,
portable report validation, bounded configuration, external occurrence locations
and history without provider invocation. The selection/result and immutable
source-binding checks also have designated security mutants.

See `docs/reference/scientific-providers.md` for the CLI/Python API, exact
diagnostics and limits. Provider provenance is retained in the Plan's existing
finite execution controls and bound by the Run's Plan digest. Frozen historical
Plan/Run schemas and canonical fixture bytes are unchanged.

Final qualification is retained in `qualification.json`. One common full suite
reported 7,822 passes and 74 expected skips. Its collection collision was resolved
by isolating this test folder as a package. The other failure was the MCP history
schema fingerprint: reviewed schemas differ only by optional provider properties
and their definitions, so its history-only fingerprint was updated. The 174
affected tests then passed; the full suite was not repeated. Combined coverage is
95.58%, with all 23 standard-platform coverage checks passing. The separate Linux
container gates remain CI responsibilities. All 166 security mutants were killed;
the three new mutants were rechecked after the test-package fix. Strict docs/HTML,
architecture, Ruff, Pyright and pre-commit checks pass.
