---
title: What does Readiness decide?
description: Read eligibility and limitations without treating static analysis as permission to execute.
---

# What does Readiness decide?

Readiness asks whether the retained source evidence is sufficient to describe
an ordinary interface for a capability under the chosen policy. The report
includes reasons for its decision, so you can see what needs attention.

| State | What to do next |
| --- | --- |
| Ready | Review the contract and choose whether to expose it. |
| Conditional | Read the unresolved binding, dependency or initialization reasons. |
| Unsupported | Use a supported callable or input shape, or a suitable adapter. |
| Ambiguous | Resolve conflicting declarations or bindings before selecting a function. |

Readiness inspects source without running your workload. Repository assessment
can use retained evidence about local imports and explicitly supplied dependency
providers; it does not silently install missing libraries.

## Ready is an eligibility decision

A ready function stays private until you select it. Readiness also does not
approve execution, guarantee successful imports or make unfamiliar code safe
to run. Unknown effects and output limitations remain in the report.

Begin with [source inspection](../getting-started/user-guide/inspect.md), then
use [repository readiness](../getting-started/user-guide/repository-readiness.md)
when your function depends on other files. The architecture guides describe
[source-local readiness](../architecture/capability-readiness-v1.md) and
[repository assessment](../architecture/repository-readiness-v1.md) in detail.

[Watch Part II: Inspect](index.md#02-inspect)

**Next chapter:** [What does Exposure select?](exposure.md)
