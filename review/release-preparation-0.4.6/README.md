# 0.4.6 release preparation — 2026-10-16

No package, site, registry, extension, tag or GitHub Release was published.
The maintainer requires explicit GitHub branch validation and a protected merge
into main/master before any publication. The site publication preflight refuses
the prepared 0.4.6 build; `site-refusal.json` retains that local refusal.

The eight local archives in `candidate.json` were built once from clean source
`745bae6ab3f04402f8dff764f9e4fd7f356801c0`. The four package versions, internal
pins, launcher and VSIX agree on 0.4.6. The 146 registry entries in `uv.lock`
are unchanged. Existing published artifacts and Homebrew publication policy
remain outside this preparation. No stable-branch change or merge was performed.

`release-metadata.json` is the exact pre-build inventory. All eight archives
retain the reviewed README bytes and Project URLs; all four sdists rebuild
autonomously. `distribution-checks.json` records those archive checks.
The retained distribution digest map is represented as file/SHA-256 rows;
no hash or qualification outcome is changed.
The existing videos, hero artwork, templates and page styles are preserved.
Rendered README previews are retained by the documentation CI job.

`installations.json` records real pip, uv tool, pipx, extras, catalog/profile and
migration qualification on macOS arm64 / CPython 3.15, with an unchanged core.
`integrated-journey.json` records the real Jupyter/installed-VSIX/CLI/SDK/REST/MCP
journey using these same archives and the same-commit VSIX: two successful Runs,
a failed cell, canonical history/show/diff, provider-independent reads, tampered
artifact refusal and zero serving-time training calls with two positive controls.
`vsix.json` retains the exact extension identity. These are local observations;
the complete hosted matrix and final protected-source qualification remain separate.

The common suite passed 7,714 tests, with 74 skips. A timing-dependent coverage
edge remained in worker cleanup. The added real-process test synchronizes an
already exited worker with a live descendant holding stdout open; it verifies
successful protocol completion, group cleanup and closed pipes without changing
production code, policy deadlines or coverage floors. All 24 cleanup/failure
checks then passed, and the existing selected-scope coverage gate passes with
100% experiment-runner lines. Overall coverage is 97.44%; all 21 package floors
pass. Python 3.11 metadata/asset tests: 73 passed. Pyright, architecture,
pre-commit and staged secret checks pass.

The following evidence commit only adds retained records, that cleanup test and
a historical label correction in the maintainer procedure. It changes none of
the candidate's frozen README/metadata inputs or production sources. Publication
preflight workflow wiring and post-publication verification in #328/#326 remain
pending; no release completion is claimed.

## Hosted Linux 3.15 follow-up

The superseded run [38905012209, job 116990841541](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/38905012209/job/116990841541)
failed while preparing the historical 0.3.0 Quickstart. That release excludes
Python 3.15. Its explicit `uv python install 3.14` inherited the consumer's
`UV_PYTHON_DOWNLOADS=never`, so the runner without an existing 3.14 installation
refused acquisition. The retained `migration.log` identifies that cause.

The helper now grants `manual` downloads only to that explicit preparation
command, then finds and runs the old host with downloads still disabled.
Two regression cases cover an existing and an absent historical host without
mutating the consumer environment. All 55 documentation/qualification tests pass.
A real isolated acquisition with `only-managed` selection and the original
`never` policy prepared Python 3.14.8 under `/private/tmp`; the original 0.3.0
Quickstart then passed its real MCP and REST calls. `historical-host.json` records
that local observation. No user interpreter or executable was replaced. The new
hosted matrix must still confirm Linux; no successful Linux result is inferred.
