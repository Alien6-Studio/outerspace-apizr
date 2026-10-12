# Share an existing business quote

A sales application needs a price and availability decision from existing Python.
Generate REST/MCP directly, without an Experiment Run.

## Expected result and prerequisites

The order receives a quote of **9,180 EUR cents**, with a fictional 20% tax and
10% launch discount. These pedagogical business rules belong to this example.

Use Python 3.11–3.14 on Linux/macOS and [Apizr core](../getting-started/install.md).
Download [business-quote.zip](../downloads/business-quote.zip), extract outside the
checkout and open `business-quote/`. Stock/products and `order.json` are fictional;
all files are GPL-3.0-or-later. Generated service requirements go in a separate
runtime. No Docker, plugin or AI account is needed.

## Files and business input

`src/api.py` defines structured `Line`, `Order` and `quote`. `inventory.py` and
`pricing.py` supply private helpers. `unfinished.py` is an independent stream
used for a real compiler refusal. Drivers are outside `src`.

```json
{"order":{"lines":[{"sku":"DESK-LAMP","quantity":3},{"sku":"NOTEBOOK","quantity":2}],"coupon":"launch"}}
```

Three lamps at 2,500 cents and two notebooks at 500 cents give 8,500. Discounted
net is 7,650; illustrative tax is 1,530; total is 9,180. Per-line stock is checked.
This quote does not reserve stock or aggregate duplicate SKU lines atomically.

## Generate both interfaces

<!-- scenario:quote-build -->
```sh
python configure.py
export BUNDLES="$(cd .. && pwd -P)/bundles"
mkdir -p "$BUNDLES"
apizr expose build rest . --source-root src --operator-policy operator.json \
  --readiness-policy readiness.json --policy exposure.json --output-dir "$BUNDLES/rest"
apizr expose build mcp . --source-root src --operator-policy operator.json \
  --readiness-policy readiness.json --policy exposure.json --output-dir "$BUNDLES/mcp"
```

`configure.py` grants only exact-root `source.analyze` and selects `python:api:quote`.
Check generated `openapi.json`/`mcp-tools.json`: helpers and stream stay private.
Only `src` is scanned; example drivers do not become bundled business source.

## Start and call REST

Startup imports trusted source. Prepare a separate service runtime:

<!-- scenario:quote-install -->
```sh
python -m venv ../runtime
../runtime/bin/python -m pip install -r ../bundles/rest/requirements.txt -r ../bundles/mcp/requirements.txt
```

<!-- scenario:quote-serve -->
```sh
../runtime/bin/python -m uvicorn app:app --app-dir ../bundles/rest --host 127.0.0.1 --port 8000
```

From a second shell in `business-quote/`:

<!-- scenario:quote-http -->
```sh
python http_client.py http://127.0.0.1:8000 order.json
```

```json
{"currency":"EUR","net_cents":7650,"ok":true,"tax_cents":1530,"total_cents":9180}
```

## Call MCP

<!-- scenario:quote-mcp -->
```sh
../runtime/bin/python mcp_client.py ../runtime/bin/python ../bundles/mcp/server.py order.json
```

The real client lists only `api.quote`, checks the quote and rejects an extra
nested input field. This generated service executes business functions; the
optional analysis MCP plugin explores repositories instead.

## Useful failure, limits and cleanup

Request 13 lamps with a valid shape: the calculation returns
`{"ok":false,"reason":"insufficient_stock"}`. Reduce quantity to verify recovery.
A string quantity/extra field instead produces HTTP 422 or an MCP tool error.
Stock is static and fictional, with no reservation or jurisdiction validation.
Stop REST with Ctrl-C; the MCP context closes its process. Remove only generated
sibling `bundles/`, `runtime/` and the extracted project. Continue with
[the public Python compiler](../developer-guide/compiler.md) for integration and
unsupported stream refusal.
