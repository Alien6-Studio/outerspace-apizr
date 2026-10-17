---
title: Architecture guide
description: Understand Apizr's components, compilation flow, optional experiment evidence, execution boundaries and service delivery.
---

# Understand Apizr's architecture

Follow a Python function from source evidence to a callable service, then see
where optional experiments, execution controls and delivery proofs fit. By the
end, you can distinguish what the compiler establishes from what the runtime,
operator and external deployment platform must provide.

This guide describes the published **Apizr 0.4.6** workflows. Schema versions
identify individual artifact contracts; they are independent of the package
version. The existing specifications remain available in the contract sections
of this guide, at their original addresses.

## Before you begin

You should be familiar with Python functions and the difference between
generating a service and starting one. No running server, Docker installation
or AI account is needed to read the diagrams. For a concrete result first,
complete [Quickstart](../getting-started/quickstart.md) or the
[business quote example](../examples/business-quote.md).

[Concepts and limits](../reference/concepts.md) defines the shared vocabulary.
Use [Reference](../reference/index.md) when you need an exact option, API field
or error rather than the relationships between components.

## Read the guide in order

| Chapter | Question it answers | What to check in your design |
| --- | --- | --- |
| [Follow the whole system](overview.md) | How does source become an interface? | Analysis, selection, generation and execution are distinct stages |
| [Components and responsibilities](system-boundaries.md) | Which component owns each operation? | Analysis MCP, generated MCP and optional extensions have different roles |
| [From source to interfaces](compilation-flow.md) | What evidence does compilation retain? | Public selection stays explicit; private helpers do not become endpoints |
| [Experiments and artifact identities](experiments-and-artifacts.md) | Where do Plans, Runs and hashes fit? | A Run is optional; recorded identities do not replace resource bytes |
| [Request and execution boundaries](execution-boundaries.md) | Which process imports and executes my code? | The selected backend supplies only its documented controls |
| [Extensions and service delivery](extensions-and-delivery.md) | How does a bundle become a verifiable handover? | Installation, authority, image delivery and proof verification remain separate |

Each diagram shows a documented relationship. Solid arrows indicate the flow
of input or a request; dashed arrows identify optional paths or additional
evidence. The accompanying text states the limits of that relationship. Wide
diagrams can be scrolled horizontally, including with the keyboard after focus.

## Find the detailed contract

The sidebar groups the existing specifications into **Static compilation**,
**Experiment evidence**, **Generation and execution**, and **Integrity and
security**. Their schemas, Python APIs, validation rules and historical context
remain the canonical details. The explanatory chapters link to those contracts
at the point where each one matters.

For implementation ownership, see [Code organization](code-organization.md)
in Contributing. The architecture guide explains product boundaries; the
contributor rule governs changes to Apizr's own packages.

Continue with [Follow the whole system](overview.md).
