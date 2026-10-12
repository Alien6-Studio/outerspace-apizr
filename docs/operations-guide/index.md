# Operate generated services

Prepare environments, run a local generated service, deliver its image and retain
verifiable evidence. Apizr is a CLI/compiler with optional extensions; it has no
SaaS administration console or central user database.

## Before you begin

Use a qualified Linux or macOS host and the [installation guide](../getting-started/install.md).
Know the source/bundle you are authorized to operate. Docker is needed for images
and OCI workers, not for static analysis, generation or direct/local REST/MCP calls.

## Follow a service through its lifecycle

1. [Environments and permissions](environments.md): keep core, extension and
   service requirements separate; grant only the operations/targets needed.
2. [Start, verify and stop](local-service.md): run a local quote service, check
   health and a real business request, then stop the exact process you started.
3. [Execution controls](execution.md): choose direct, fresh local process or a
   prepared OCI worker according to the exact available controls.
4. [Build and deliver](delivery.md): preserve build/transfer results, optionally
   verify Attest proof and hand documents to your deployment platform.
5. [Configuration and evidence](evidence.md): retain sensitive local records with
   a verified, quiescent backup procedure.
6. [Troubleshooting](troubleshooting.md): diagnose by symptom and check recovery.

## Verify the boundary you need

An image build is not a registry push. A verified push is not a started service.
An Attest receipt binds the documented delivery evidence, not scientific quality
or organizational approval. A remote deployment belongs to your platform and its
explicit authority. The [delivery example](../examples/verified-delivery.md) uses a
local disposable registry and demonstration trust, with no remote publication.

Begin with the [quote bundle](../examples/business-quote.md). Its first useful
local result requires no Docker or plugin. Keep the old runtime available until
you have verified a candidate update through your host deployment procedure.
