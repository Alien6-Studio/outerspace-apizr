# A/B capability evidence

The two `pricing.total` variants are deterministic trusted sample business code.
They have the same logical ID and input/output contract, but different descriptions,
source/bundle identities and handling fees: `total(100, 2)` returns 300 or 350.

Run `python -I scripts/governance_evidence_proof.py --output /fresh/output` with
Apizr 0.4.4 installed. The script generates REST/MCP bundles, exports their
existing JSON documents, invokes the trusted sample, deletes generated business
code, and verifies the exported evidence against its selected bundle digests.
`comparison.json` retains identities and actual call results.

This is a local example, not a registry or Trunx end-to-end test. For the CI
handoff, immutable OCI consumption, external decision boundary and the separate
registry qualification, see `docs/reference/external-governance.md`.
