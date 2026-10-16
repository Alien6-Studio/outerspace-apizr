# Frozen reference outputs from 0.4.5

These canonical record exports and JSON/text comparison were produced by the
exact `v0.4.5` source (`da74e6de5800eab9c275e42c5d4c24a59ac4fcbe`) reading the
unchanged real captured store in `../published-0.4.5/`. They are reference outputs,
not executions of a new workload. The producer source was loaded from a separate
tag snapshot and its import path asserted before generating these files.

`provenance.json` retains the original store provenance and per-output hashes.
The installed 0.4.6 development engine must read the exact Plan/Run values and
show/export/diff them byte-identically. Historical unknown provider provenance
must remain omitted. A newer mixed-store list view is an explicitly documented
API change, so list output is not asserted identical to the old CLI's view.
