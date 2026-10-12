# Give a client a delivery-route calculation

Calculate a proposed visit order through a real MCP tool call, without a simulated
assistant answer.

## Expected result and prerequisites

The supplied stops produce `warehouse → library → cafe → museum → warehouse`
and **12 estimated minutes**. This educational example uses fictional coordinates
and Manhattan distance as minutes. It is distinct from the
[recorded Paris demonstration](../index.md#watch-apizr-in-action), with no live
traffic, optimum guarantee or universal savings claim.

Use Python 3.11–3.14, [Apizr core](../getting-started/install.md) and a separate MCP
runtime. Download [logistics-tool.zip](../downloads/logistics-tool.zip), extract
outside the checkout and open `logistics-tool/`. Files are `route.py`, `stops.json`
and real `client.py`; data/algorithm are pedagogical GPL-3.0-or-later. No external
routing service, analysis plugin or paid account is used.

## Choose one public tool

<!-- scenario:route-build -->
```sh
export ROUTE_BUNDLE="$(cd .. && pwd -P)/route-bundle"
apizr inspect route.py
apizr generate mcp route.py --select plan_route --output-dir "$ROUTE_BUNDLE"
```

`_minutes` stays private. `plan_route` uses nearest-neighbour selection with a
lexical tie-break. Apizr supplies the adapter, not the algorithm or a model decision.

## Call the generated calculation

Starting the server executes trusted source; the client owns its stdio process.

<!-- scenario:route-call -->
```sh
python -m venv ../route-runtime
../route-runtime/bin/python -m pip install -r ../route-bundle/requirements.txt
../route-runtime/bin/python client.py ../route-runtime/bin/python ../route-bundle/server.py
```

The official MCP client initializes, lists only `plan_route`, calls
`{"stops":["museum","cafe","library"]}` and asserts:

```json
{"ok":true,"route":["warehouse","library","cafe","museum","warehouse"],"estimated_minutes":12}
```

An assistant may optionally choose this tool and its arguments; the essential
calculation runs without one. No simulated model response is involved.

## Useful failure, limits and cleanup

The client also calls `{"stops":["unknown"]}` and checks
`{"ok":false,"reason":"unknown_stop"}`. Supply known unique stops to correct it.
Duplicate/empty lists have another business refusal; non-string members are MCP
contract errors. The greedy algorithm need not find an optimum, fictional minutes
are not measurements, and vehicle constraints are absent. The context stops its
server. Remove only the extracted project, `route-bundle/` and `route-runtime/`.
