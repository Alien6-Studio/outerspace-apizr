---
title: "Existing Python. A real REST API."
description: Expose two functions from keon/algorithms and verify successful calls and HTTP 422.
lesson: 3
recording: 03-rest
---

<p class="apizr-academy-kicker">Build interfaces · Lesson 03</p>

<span id="generate-a-rest-api-for-gcd-and-lcm"></span>

# Existing Python. A real REST API.

The recording turns existing number-theory functions into two REST endpoints. It uses **keon/algorithms** and checks both arithmetic results and invalid input. This is a different repository from Requests in lesson 2.

!!! abstract "By the end of this lesson"
    - Select only gcd and lcm from an existing Python module.
    - Separate generated files from the running service environment.
    - Verify real HTTP results and a rejected request.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=QdtaLoc-g6o" data-apizr-video="QdtaLoc-g6o" data-apizr-title="Existing Python. A real REST API." aria-label="Play: Existing Python. A real REST API.">
    <img src="../../assets/videos/academy-03-youtube.jpg" width="1280" height="720" loading="lazy" alt="Lesson 03: Existing Python. A real REST API." />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

<!-- recording-transcript -->

## 1. Inspect the recorded arithmetic module

With the video's Apizr 0.4.3 environment, obtain its exact source revision:

```sh
git clone --depth 1 https://github.com/keon/algorithms.git
cd algorithms
git fetch --depth 1 origin bd1d152f9ec7331c69be662831610b003b10fc7a
git checkout bd1d152f9ec7331c69be662831610b003b10fc7a
apizr inspect algorithms/math/gcd.py > inspection.txt
```

Both selected functions accept two integers. Their static input contract is ready, while effects remain unknown. The recording uses direct execution after reviewing this small arithmetic module.

## 2. Generate only the selected routes

```sh
apizr generate rest algorithms/math/gcd.py --select gcd,lcm --output-dir rest
uv venv --python python3.14 runtime
uv pip install --python runtime/bin/python -r rest/requirements.txt
runtime/bin/uvicorn app:app --app-dir rest --host 127.0.0.1 --port 8814
```

Generation writes source, adapters, OpenAPI and runtime requirements. The final command starts the server and imports the trusted source. Keep that terminal running while calling it from another terminal.

## 3. Reproduce the three observed requests

```sh
curl -sS http://127.0.0.1:8814/capabilities/gcd -H 'Content-Type: application/json' -d '{"a":48,"b":18}'
curl -sS http://127.0.0.1:8814/capabilities/lcm -H 'Content-Type: application/json' -d '{"a":8,"b":12}'
curl -sS -o invalid.json -w 'HTTP %{http_code}\n' http://127.0.0.1:8814/capabilities/gcd -H 'Content-Type: application/json' -d '{"a":"48","b":18}'
```

The retained terminal shows **6**, **24**, then **HTTP 422** with `Value does not match the declared input type`. The string `"48"` is rejected instead of silently becoming an integer. Stop the foreground server with Ctrl+C after practising; the recording starts it in the background and stops its saved process ID.

## Practice

Predict the two valid arithmetic results before calling the endpoints. Then send the invalid string input and explain where it is rejected. Check `rest/openapi.json`: which two functions became routes, and which helpers did not?

??? success "Check your reasoning"

    The greatest common divisor of 48 and 18 is 6; the least common multiple of 8 and 12 is 24. The generated request contract rejects the string with HTTP 422. Selection exposes only gcd and lcm. A successful local call verifies this interface, while a production deployment remains a separate task.

<span id="1-keep-the-selection-explicit"></span>
<span id="2-generate-then-run"></span>

[Back to the Academy](index.md) · [Continue to the next lesson](mcp.md)
