# Dependency maintenance policy

Changes to dependencies are reviewed through the protected pull-request process,
including Dependabot updates. An available update is not an instruction to merge
it. Keep runtime dependency changes separate from release and documentation work.

## Sources and integrity

All third-party locked packages must resolve from `https://pypi.org/simple`.
Distribution URLs must use HTTPS on `files.pythonhosted.org`, with SHA-256 hashes
recorded in `uv.lock`. The only local editable package is Apizr itself at `.`.
Git dependencies, arbitrary indexes, direct URLs and additional local packages are
rejected by `scripts/check_dependency_sources.py` in the required dependency job.
A source exception requires an explicit policy change in a reviewed PR; there is
no automatic fallback index.

Export and audit the complete universal lock, including Python/platform variants,
for runtime, development, documentation and security tooling. Findings and report
collection failures block. Do not silently add ignored advisories. Preserve the
reports and review the runtime and validation SBOMs when a graph changes.

## Licenses and package selection

Before adding or changing a dependency, review its license and required notices
at the **selected version**, its source, maintenance status, purpose and transitive
cost. Record that review in the dependency PR. Preserve license/attribution files
required for redistribution. Reject dependencies with no identified license or
terms incompatible with the intended GPL-3.0-or-later distribution until a
maintainer has resolved the issue and recorded the decision. Do not treat package
metadata or an SBOM entry as a legal compatibility determination.

The required `dependencies` job runs `scripts/check_dependency_licenses.py`.
Its reviewed baseline covers all **138 third-party versions** in the universal
lock, including platform alternatives and all four dependency groups:

- `policy/dependency-licenses.json` records component expressions, review scope,
  notes, the exact evidence archive and its license-file hashes.
- `policy/dependency-license-texts.json` preserves 196 distinct UTF-8 notice texts
  from 257 archive paths, including original line endings inside JSON strings.
- `policy/dependency-policy.json` defines the SPDX allowlist, version-specific
  exceptions and named-package denials with upstream references.

The gate rejects missing, duplicate, stale or pending reviews; any change to the
locked archive URL/hash set; missing or altered notice texts; unknown or denied
license expressions; unsubstantiated or stale exceptions; and denied package
names (including normalized spelling variants). `AND` requires every term; `OR`
permits a licensed choice. A `WITH` exception is allowed only as an explicitly
listed license/exception pair. Package metadata never grants automatic approval.

The denylist rejects the deprecated `sklearn` and removed `tensorflow-gpu`
installation placeholders. Their maintained replacements require ordinary
review; absence from this short denylist is not an approval. Vulnerability and
source checks remain separate, mandatory gates.

### Scope and obligations

These decisions admit unmodified dependencies for Apizr's existing uses. Apizr's
wheel and sdist do **not** embed the dependency packages. The initial review
examined one hash-verified source archive per version, or one locked Windows
wheel for pywin32. Other wheel hashes are bound to the decision, but their
contents were not exhaustively inspected. This is not a file-level legal audit
or a complete inventory of native libraries, Cargo/npm dependencies, OS packages,
nested wheels or tools downloaded outside `uv.lock`.

| Component | Recorded obligation or limit |
| --- | --- |
| Python-derived code | Retain the complete historical Python notices, not just a PSF metadata label. |
| MPL packages and certifi data | Preserve notices and applicable source availability obligations; no automatic relicensing is asserted. |
| license-expression data | CC-BY-4.0 attribution; a separate, evidence-backed public-domain declaration for copied algorithm code. |
| Material theme assets | Distinct font/icon licenses and attribution; individual icon/brand restrictions still apply. |
| pywin32 | BSD/MIT/Python/Scintilla notices plus LGPL 2.1 for adodbapi; do not strip these or ignore source/relinking obligations. |
| Native and nested packages | cryptography, pyzmq, cffi, Rust extensions and virtualenv need an exact-content review before binary redistribution. |

The eight exceptions are confined to the named versions and preserved evidence;
they do not globally allow these terms for arbitrary packages. Before publishing
containers, vendoring dependencies, modifying third-party code or selecting new
documentation assets, review the actual contents and meet their notice, source,
attribution, font and trademark obligations. This gate alone does not authorize
such distributions. The evidence includes unused upstream documentation and
test-fixture notices; those are not silently treated as the package's license.

### Review an update

1. Update the dependency and universal lock in a dedicated PR.
2. Collect candidate notices without installing or executing the package:

   ```sh
   uv run --locked python scripts/collect_dependency_licenses.py \
     --package example --output /tmp/example-license-candidate.json
   ```

3. Read the archive notices and component terms. Resolve missing/ambiguous
   licenses; identify copied code, data, fonts, native components and obligations.
   The collector always writes `pending` and never edits approved policy.
4. Update the corresponding inventory, texts and any narrowly justified policy
   exception. The distribution fingerprint is SHA-256 of the sorted URL/hash
   set and source, as defined by `distribution_fingerprint` in the checker.
   Remove obsolete entries. Never approve a new version solely by copying its
   predecessor's expression or by reading PyPI metadata.
5. Run the source and license checkers, dependency audit and normal PR checks.
   A protected PR records adoption of the review; this does not assert an
   independent legal certification or independent human review.

The package build archives policy, inventory, notice texts and their check report
alongside the source, lock and SBOMs. The Security artifact also contains the
license result and hashes of all inputs. They become part of release evidence.

References: [SPDX expression syntax](https://spdx.github.io/spdx-spec/v3.0.1/annexes/spdx-license-expressions/),
[Apache's GPLv3 compatibility guidance](https://www.apache.org/licenses/GPL-compatibility),
[Mozilla's license policy](https://www.mozilla.org/en-US/MPL/license-policy/),
[sklearn deprecation](https://pypi.org/project/sklearn/) and
[tensorflow-gpu removal](https://pypi.org/project/tensorflow-gpu/).
