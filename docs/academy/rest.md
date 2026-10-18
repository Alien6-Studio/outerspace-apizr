---
title: Turn a selected function into a REST call
description: Connect Python arguments, an HTTP request and an observed response.
lesson: 3
---

<p class="apizr-academy-kicker">Build a service · Lesson 03 · Plan about 25 min</p>

# Turn a selected function into a REST call

A browser application needs a price, not access to every function in your repository. You will expose the two reviewed shop capabilities and follow one request through to its result.

The useful test is a complete call: a described endpoint, a running local server, a request with the right inputs and an observed response.

!!! abstract "By the end of this lesson"
    - Distinguish interface generation from starting a server.
    - Connect a JSON request to the selected Python arguments.
    - Check the result and recognize what a local successful call leaves undecided.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=QdtaLoc-g6o" data-apizr-video="QdtaLoc-g6o" data-apizr-title="Generate a REST API and make HTTP calls" aria-label="Play: Generate a REST API and make HTTP calls">
    <img src="../../assets/videos/tutorial-rest.jpg" width="480" height="360" loading="lazy" alt="Academy Part III: generate and call REST" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

English · 4:14 · The written steps below target 0.4.6 development; the recording keeps its original demonstrated version.

## 1. Keep the selection explicit

Use the [shop workspace preparation](../getting-started/quickstart.md#prepare-an-isolated-workspace) through “Get the example and choose its public functions”. It gives you `shop/`, a separate `runtime/` environment and the three policy files. The selection contains `api.quote` and `inventory.available`; private helpers do not become extra endpoints.

The readiness policy describes the eligible interface. The exposure policy selects capabilities and an execution mode. The operator policy grants analysis of this exact local directory. These files answer different questions.

## 2. Generate, then run

From that workspace, build the REST bundle and install its declared runtime requirements:

```sh
apizr expose build rest shop --operator-policy operator.json --readiness-policy readiness-direct.json --policy exposure-direct.json --output-dir build/rest
runtime/bin/python -m pip install -r build/rest/requirements.txt
runtime/bin/uvicorn app:app --app-dir build/rest --host 127.0.0.1 --port 8000
```

Generation writes the adapter and its OpenAPI description. The last command actually starts the service. Direct-mode calls execute your trusted Python with the server process’s host permissions.

In a second terminal, send a request:

```sh
curl --fail --silent --show-error http://127.0.0.1:8000/capabilities/api.quote   --header 'Content-Type: application/json'   --data '{"unit_price":12.5,"quantity":2}'
```

The expected body is `25.0`: `12.5 × 2`. Inspect `build/rest/openapi.json` and the local `/docs` page to connect the selected operation, input names and supported shapes.

## Practice

1. Predict the result for `unit_price=12.5` and `quantity=3`, then make that call.
2. Call the selected stock function with `stock=10` and `requested=13` using the [second quickstart request](../getting-started/quickstart.md#use-rest-instead).
3. Explain why these local calls are insufficient evidence that a public production deployment is ready. Stop the server with Ctrl+C.

??? success "Check your reasoning"

    The new price is `37.5`; the stock check returns `false`. These are observations of the selected business functions through the generated adapter.

    You have exercised a local interface. Deployment, authentication, application authorization, operational limits and availability still need their own design and checks. Generating an endpoint does not settle those responsibilities.

[Back to the Academy](index.md) · [Continue to the next lesson](mcp.md)
