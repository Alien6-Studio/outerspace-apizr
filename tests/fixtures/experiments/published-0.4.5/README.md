# Frozen 0.4.5 store

These two successful Runs were produced by `run_experiment` using the frozen
release source commit `da74e6de` (0.4.5), executing the trusted fixture
`score = 0.75` with the explicit metric binding `score=score` on Python 3.12.
The canonical source reference is `train.py`. They contain real producer timing
and bounded interpreter metadata, with no absolute project paths or credentials.

The files in `plans/` and `runs/` are the original store bytes. `sha256.json`
records their identities and release-source provenance. Treat them as immutable:
v2 readers and history/comparison must continue to read these exact v1 bytes.
