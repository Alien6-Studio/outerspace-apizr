# Consume HTTP and MCP interfaces

Call the same Python calculation from an HTTP application and a tool client.
Verify the actual public names, response and invalid input handling.

## Before you begin

Generate the [quote example](../examples/business-quote.md) or
[Python compiler example](compiler.md). Install the emitted transport requirements
in a separate service environment. Run only trusted bundled code and dependencies.
The example contains complete `http_client.py` and `mcp_client.py` files.

## Call HTTP

Start the quote REST bundle using the [local lifecycle procedure](../operations-guide/local-service.md).
From the extracted example:

```sh
python http_client.py http://127.0.0.1:8000 order.json
```

The client sends `POST /capabilities/api.quote`, validates the JSON response and
prints it. HTTP 422 is input-shape failure; the example's `ok:false` response is a
business refusal. An unexpected function exception becomes a generic 500, not an
invitation to send source exception messages to clients.

## Call a generated MCP tool

The MCP client initializes a stdio session and checks the real tool inventory:

```sh
../runtime/bin/python mcp_client.py ../runtime/bin/python ../bundles/mcp/server.py order.json
```

The server is started by the client and closed when its context exits. There is no
separate background stdio server to manage. `result.is_error` signals a tool error;
`structured_content` contains the business object. Scalar results instead use
`{"result": value}`. The quote's object remains an object.

MCP Tool names include modules for repository bundles (`api.quote`), whereas a
single-source generated tool uses the selected symbol (`plan_route`). Read the
emitted tool list instead of assuming a name.

## Distinguish tool execution from assistant decisions

These calls use the official Python MCP SDK and need no AI account. An assistant
may choose a tool and arguments, but the calculation is performed by your
function through MCP. The [route example](../examples/logistics-tool.md) makes
that distinction visible without a simulated model response.

The optional [analysis MCP plugin](../reference/apizr-mcp-server.md) supplies Apizr
repository-analysis tools, not your business functions. Configure it separately
if your integration needs exploratory analysis.

## Add access controls in your deployment

The tutorials bind HTTP locally and use trusted code. Before remote access, your
platform must provide authentication, authorization and lifecycle controls.
Generated contracts and a successful local call do not implement organization
permissions. Continue with [operations](../operations-guide/index.md).
