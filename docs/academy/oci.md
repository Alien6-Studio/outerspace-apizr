---
title: Build an MCP image and let Ollama call pricing.total
description: Follow the recorded OCI plugin build and the actual local model-to-container tool call.
lesson: 5
recording: 05-oci-ollama
---

<p class="apizr-academy-kicker">Build interfaces · Lesson 05</p>

# Build an MCP image and let Ollama call pricing.total

This video joins four concrete components: the repository shop, Apizr's OCI plugin, a generated MCP container and a small Ollama bridge. Its result is a real tool request for **7 items at 19.5**, returning **136.5**.

!!! abstract "By the end of this lesson"
    - Distinguish a repository MCP bundle from lesson 4's single-file bundle.
    - Identify the explicit inputs and permission for an OCI image build.
    - Follow a real Ollama request through the MCP client into the container.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=_PwRZeBN1fM" data-apizr-video="_PwRZeBN1fM" data-apizr-title="Generate an OCI image. Call MCP with Ollama." aria-label="Play: Build an OCI image and call its MCP tool with Ollama">
    <img src="../../assets/videos/tutorial-oci.jpg" width="480" height="360" loading="lazy" alt="Academy Part V: build an OCI service image" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

<!-- recording-transcript -->

## 1. Read the recorded setup

The recording uses **Apizr and OCI plugin 0.4.3**, Python 3.14, Apple Silicon, Docker Desktop with Buildx, a prepared Python base image and the local `qwen3-coder:30b` Ollama model. Plugin wheels, their hashes and the complete dependency lock are prepared before the filmed operations.

Download the [original OCI/Ollama teaching files](../downloads/academy-oci-ollama.zip) into a fresh workspace. They contain the original build helper, bridge, image verifier, recorded commands and the two policies. The helper retains the recording's Docker Desktop and ARM64 assumptions; review paths and target platform for your own machine. The [OCI reference](../reference/oci-service-plugin.md) supplies the current preparation procedure as a separate setup reference.

## 2. Select the repository shop and build the image

The video clones Apizr's `v0.4.3` source and selects **`python:pricing:total`** from `source/examples/repository-shop`. It explicitly installs and enables the OCI plugin in a separate plugin store. The recorded commands and required wheel digest appear in the transcript below.

```sh
apizr init source/examples/repository-shop
apizr expose build mcp source/examples/repository-shop --operator-policy source/examples/repository-shop/.apizr/operator.json --readiness-policy readiness.json --policy exposure.json --output-dir mcp-bundle
python prepare_build.py
apizr plugins run outerspace-apizr-oci build --arguments build.json --operator-policy build-operator.json --plugins-dir "$PWD/plugins" --timeout-ms 360000 > build-result.json
```

`prepare_build.py` downloads target-runtime wheels and writes their lock, the build request and a matching operator grant. The Apizr plugin generates the Dockerfile and performs the build. Its result has **`published: false`**: this is a local image, not a registry push.

## 3. Follow the model's actual tool call

The original bridge discovers the container's MCP schemas, passes them to Ollama's chat API, forwards the requested arguments through MCP and returns the tool result to Ollama. It starts the container with interactive stdin and no terminal allocation; no HTTP port is published.

```sh
uv venv --python python3.14 client
uv pip install --python client/bin/python 'mcp==2.3.0'
client/bin/python ollama_mcp.py list
client/bin/python ollama_mcp.py
python verify_image.py
```

The retained trace shows `pricing.total` called with `quantity=7` and `unit_price=19.5`, followed by `{"result": 136.5}`. The bridge stores `ollama-trace.json`. The verifier compares the actual Docker image with the Apizr result, checks user `65532:65532`, and checks that the image was not published.

## Practice

Trace the four handoffs in the recording: reviewed source → repository MCP bundle → local image → Ollama/MCP call. Locate the tool arguments, returned value and image identity. Which component chooses the call, which executes Python, and which builds the image?

??? success "Check your reasoning"

    Ollama requests a tool; the Python bridge carries that request through MCP; the generated server runs `pricing.total` inside the container. Apizr and its OCI plugin produce the bundle and image. The observed result is 136.5. A model sentence alone would not establish that the tool ran; retain the actual request/result trace and matching image identity.

<span id="1-name-the-thing-you-are-moving"></span>
<span id="2-follow-the-current-build-recipe"></span>

[Back to the Academy](index.md) · [Continue to the next lesson](experiment-inspection.md)
