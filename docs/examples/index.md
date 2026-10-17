# Choose an executable example

Choose the outcome you need. Every scenario provides complete files, prerequisites,
commands, results to check, a useful failure, limits and cleanup. Downloads are
built from this documentation revision, including new files that are not in the
historical release tag. Commands use public **Apizr 0.4.6**.

| Goal | Scenario | Prerequisites | Result |
| --- | --- | --- | --- |
| Understand changed results | [Compare fraud experiments](compare-fraud.md) | Notebook + scientific workload | Recorded differences |
| Share a model | [Share a prediction](share-prediction.md) | Matching Run/model + REST/MCP runtime | Real prediction |
| Reuse existing business logic | [Share a quote](business-quote.md) | Core + service runtime | Stock-aware quote; no Run |
| Give a client a calculation | [Calculate a route](logistics-tool.md) | Core + MCP runtime | Computed tour |
| Serve unfinished research | [Reuse independent research](research-serving.md) | Core + REST/MCP runtime | Selection and helper refusal |
| Hand over a service | [Verified local delivery](verified-delivery.md) | Docker/Buildx + OCI, optionally Attest | Image/registry/proof identities |

Use [Install Apizr](../getting-started/install.md) once for your workflow.
Scientific algorithms and business rules belong to the examples, not Apizr.
