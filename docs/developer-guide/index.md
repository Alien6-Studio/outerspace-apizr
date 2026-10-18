# Build with Apizr

Integrate Apizr into an application or development tool. You will prepare a small
business project, compile an explicit selection through the public Python API,
call both interfaces and retain reviewable artifacts in CI.

## Before you begin

Use the [core installation](../getting-started/install.md), Python 3.11–3.15 and
a trusted project you can inspect. Transport dependencies belong to the generated
service. You do not need to modify Apizr or install the analysis MCP plugin.

## Progress through a concrete integration

1. [Prepare functions and modules](functions.md): start with a structured order,
   a private inventory helper and a price policy. Inspect the actual generated
   OpenAPI/tool contract before generalizing types.
2. [Compile from Python](compiler.md): prepare one explicit selection, render
   REST and MCP from retained evidence, handle a real refusal and test results.
3. [Consume the interfaces](clients.md): send HTTP JSON and initialize a real
   MCP session. Tool calculation works without an AI account.
4. [Validate in CI](../getting-started/user-guide/ci-integrations.md): retain
   readiness, plan and generated artifacts without executing project code.
5. [Regenerate safely](regeneration.md): keep reviewed bundles distinct from
   runtime environments and client edits.
6. [Extend Apizr](extensions.md): invoke an installed demonstration through the
   supported modern extension protocol.

## Keep integration responsibilities explicit

Your application owns the calculation, its business validation, data and tests.
Apizr owns source analysis, selection, generated contracts and their documented
integrity checks. Your deployment platform owns authenticated remote access,
organizational promotion and service operation.

The quote scenario uses fictional stock, EUR cents and an illustrative 20% tax.
Those rules belong to the example, not Apizr. The generated adapter validates the
closed order object, then calls that Python calculation.

An operator policy grants repository reads at the point you compile. If you fetch
Git, [Git acquisition](../reference/git-sources.md) needs its own grant for one
reviewed revision; a branch name or project configuration does not silently grant
that permission.

To change Apizr itself, use [Contributing](../about/CONTRIBUTING.md). Its package
organization, coverage and publication procedures are separate from this guide.
