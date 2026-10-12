# Prepare functions and modules

Design a stable public entry point over existing Python logic. The result is a
small contract clients can understand while your helpers remain implementation
support.

## Before you begin

Download and extract the [quote project](../examples/business-quote.md). The core
can inspect/generate it without importing its business modules. Start from the
example's explicit policies and analysis grant.

## Look at the concrete contract

`api.quote(order: Order)` accepts:

```json
{"order":{"lines":[{"sku":"DESK-LAMP","quantity":3},{"sku":"NOTEBOOK","quantity":2}],"coupon":"launch"}}
```

Its successful result contains `currency`, `net_cents`, `tax_cents`, and
`total_cents`. The example returns 9,180 EUR cents including illustrative tax.
Read `openapi.json` after generation: `order` and nested line objects are closed,
`sku` and `quantity` are required, and coupon is `none` or `launch`. MCP advertises
the same input shape. A string quantity is refused before business execution.

## Keep helpers private

The project has `api.py`, `inventory.py` and `pricing.py`. Repository compilation
resolves their supported local imports. Select only `python:api:quote`; including
`product`, `discounted` and `tax` in the source bundle does not create public routes.
A private helper need not have a public input contract of its own.

With a `src/shop` package, choose `src` as source root; use an empty `__init__.py`
and supported relative imports. A nonempty initializer without callable readiness
evidence can remain conditional. Dynamic, star or rebound imports are conservative
and can block required dependencies.

## Use types Apizr actually understands

Supported stdlib class-form TypedDicts must have an unambiguous earlier typing
import and supported fields. `Line` is declared before `Order` in the same module.
Do not assume arbitrary dataclasses, Pydantic models, quoted forward references,
recursive types or methods receive the same treatment. See the exact
[type vocabulary](../architecture/capability-readiness-v1.md#input-and-output-contracts).

Defaults preserve omission versus explicit null. A nullable annotation accepts
null; a default `None` alone does not make an integer annotation nullable.
Declared return types describe the interface, while runtime serialization has its
own finite-JSON rules. Use a finite business result and test it through each
transport, particularly when changing tuples or third-party scalar types.

## Separate import from work

Keep long-running training and application startup outside required module
initialization. A uniquely resolved import still needs sufficient evidence about
its required helper and initializer. Use the [research scenario](../examples/research-serving.md)
to see an independent unfinished experiment alongside a refused required helper.

Continue with [the compiler integration](compiler.md).
