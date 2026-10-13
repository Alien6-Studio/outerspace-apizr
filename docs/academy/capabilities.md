---
title: What is a capability?
description: Understand which Python functions Apizr can describe before choosing a public interface.
---

# What is a capability?

A capability describes a Python function that a client could call: its logical
name, parameters, defaults, return annotation and source evidence. For example,
a price function accepts a unit price and quantity and returns a total.

Apizr reads source to describe that contract. It does not call the function or
import your project during static inspection. A declaration can be visible in
the report while its interface remains conditional or unsupported.

## Start with one useful result

Follow the [Quickstart](../getting-started/quickstart.md) to turn the price and
stock functions into working calls. To inspect your own file first, use the
[inspection guide](../getting-started/user-guide/inspect.md).

The capability's name identifies the function. A private helper used by that
function can be included in a generated bundle without receiving an endpoint
or tool of its own.

## What the description establishes

The report retains the interface evidence found in your source. Missing
annotations or uncertain Python bindings stay visible as limitations. A return
annotation describes an expected shape; it does not prove the implementation
returns that value or that the result is scientifically correct.

For the complete model, see [Capability IR](../architecture/capability-ir-v1.md)
and the [compiler overview](../architecture/overview.md).

[Watch the demonstration](index.md#00-see-the-result) ·
[Watch Part II: Inspect](index.md#02-inspect)

**Next chapter:** [What does Readiness decide?](readiness.md)
