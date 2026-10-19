---
title: "Existing Python. Real MCP tools."
description: Discover two generated colour-conversion tools, make real calls and read an error.
lesson: 4
recording: 04-mcp
---

<p class="apizr-academy-kicker">Build interfaces · Lesson 04</p>

<span id="call-rgb-and-hsv-conversions-through-mcp"></span>

# Existing Python. Real MCP tools.

The video uses **TheAlgorithms/Python** to convert colours. A Python MCP client makes discovery, successful results and input errors visible without requiring a language model.

!!! abstract "By the end of this lesson"
    - Select rgb_to_hsv and hsv_to_rgb while keeping their helper private.
    - Explain the stdio client/server lifecycle.
    - Check the error flag before reading structured_content.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=rJThRd9vq4g" data-apizr-video="rJThRd9vq4g" data-apizr-title="Existing Python. Real MCP tools." aria-label="Play: Existing Python. Real MCP tools.">
    <img src="../../assets/videos/academy-04-youtube.jpg" width="1280" height="720" loading="lazy" alt="Lesson 04: Existing Python. Real MCP tools." />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

<!-- recording-transcript -->

## 1. Pin and generate the recorded module

The video uses Apizr 0.4.3 and this exact repository revision:

```sh
git clone --depth 1 https://github.com/TheAlgorithms/Python.git
cd Python
git fetch --depth 1 origin ef2ecc4d34d17ce6249ba5d3f3c17822dfd7bd50
git checkout ef2ecc4d34d17ce6249ba5d3f3c17822dfd7bd50
apizr inspect conversions/rgb_hsv_conversion.py > inspection.txt
apizr generate mcp conversions/rgb_hsv_conversion.py --select rgb_to_hsv,hsv_to_rgb --output-dir mcp
uv venv --python python3.14 runtime
uv pip install --python runtime/bin/python -r mcp/requirements.txt
```

The inspected module has three ready functions. The selection makes the two conversions public; the comparison helper remains outside the tool list. Generating the bundle does not start its server.

## 2. Use the recorded client

Download the [original call_tools.py](../downloads/academy-mcp-client.py), saving it beside `mcp/` as `call_tools.py`. This is the actual client used in the recording. Its `StdioServerParameters` selects the current runtime interpreter and the generated server. The client context performs connection and handshake before discovery or a call.

```sh
runtime/bin/python call_tools.py list
runtime/bin/python call_tools.py red
runtime/bin/python call_tools.py green
runtime/bin/python call_tools.py invalid
```

| Operation | Retained response |
| --- | --- |
| List tools | `hsv_to_rgb`, `rgb_to_hsv` |
| RGB red: 255, 0, 0 | `{"result": [0.0, 1.0, 1.0]}` |
| HSV green: 120, 1, 1 | `{"result": [0, 255, 0]}` |
| Red channel passed as a string | `is_error: True`, `structured_content: null` |

These are actual server results. Tool discovery and tool invocation are separate protocol operations. A model's later prose is not a replacement for either.

## Practice

Predict both colour conversions, verify that only the two selected tools are listed, and run the invalid-input case. Explain why checking only whether a response object exists would miss the error.

??? success "Check your reasoning"

    Red has hue 0, saturation 1 and value 1. HSV hue 120 gives RGB green. The invalid string returns an error and no structured result. Check `is_error` before interpreting `structured_content`; a completed protocol exchange can carry a failed tool call.

<span id="1-reuse-the-shop-selection"></span>
<span id="2-observe-discovery-and-a-real-call"></span>

[Back to the Academy](index.md) · [Continue to the next lesson](oci.md)
