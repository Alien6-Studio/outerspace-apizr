---
template: home.html
title: Apizr — capability compiler for Python
description: Discover capabilities, assess readiness, explicitly select public interfaces and execute Python repositories through REST or MCP.
---

# Apizr

Connect selected Python functions to AI agents through MCP,
or expose them as REST APIs.

Apizr is an **open-source capability compiler**. It analyzes existing Python code,
lets you choose the public functions, generates their interfaces, and lets you
define how they execute. Keep your business logic in Python and connect it to
agents or applications.

[Quickstart: MCP and REST calls](getting-started/quickstart.md){ .md-button .md-button--primary }
[The full journey](getting-started/introduction.md){ .md-button }

**Latest published stable: 0.3.0 · Released 22 September 2026**

**Preparing 0.4 — not released.** Use the stable Quickstart above for your first
server. The [0.4 development guide](development/0.4.md) covers the compiler API,
project files, remote Git, isolated plugins and OCI/Attest delivery; those features
are not in stable 0.3.0. Python 3.11–3.14 · GPL-3.0-or-later.

  <section class="apizr-demo-section md-typeset" aria-labelledby="watch-apizr-in-action">
    <div class="apizr-demo-section__inner">
      <h2 id="watch-apizr-in-action">From Python code to REST and MCP</h2>
      <p>Bring existing Python expertise into your applications and AI workflows. See how Apizr turns a route optimizer into callable interfaces.</p>
      <div class="apizr-demo-video">
        <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=u8e0fi2m80M" data-apizr-video="u8e0fi2m80M" aria-label="Play the Apizr demonstration on YouTube">
          <img src="assets/videos/paris-route.jpg" width="1920" height="1080" loading="lazy" alt="Your expertise. Ready to connect. Apizr demonstration." />
          <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the demo</span>
        </a>
      </div>
      <p class="apizr-demo-section__language">English narration · English captions</p>
      <details class="apizr-demo-transcript">
        <summary>Read the transcript</summary>
        <div class="apizr-demo-transcript__body">
          <p><strong>Put your business logic to work.</strong> For an operations team, time on the road matters. Your Python code already plans better routes. Apizr helps make that expertise available to the people and systems that need it.</p>
          <p><strong>Keep the expertise you already have.</strong> Here, a specialist has prepared a route optimizer in a notebook. The next step is to connect it to the dispatch application, using the same calculation.</p>
          <p><strong>Understand what you can expose.</strong> First, inspect the notebook with Apizr. It identifies the functions and reports which can generate an interface. Your team chooses the capability to make available.</p>
          <p><strong>Connect your operational applications.</strong> Select the route optimizer and generate REST. Apizr creates the application and its API contract. The dispatch system now has an interface it can call.</p>
          <p><strong>Generated code your team can inspect.</strong> These are the generated files. Your developers can inspect and run them. The adapter connects incoming requests to your existing function, keeping the business calculation in one place.</p>
          <p><strong>Put the generated API to work.</strong> Start the generated application and send a list of stops. The response contains a proposed route and its driving estimate. This is what the dispatch interface will use.</p>
          <p><strong>See the operational impact.</strong> Now the result becomes visible. On this eight-stop example, the estimated driving time drops from about one hundred and one minutes to forty eight.</p>
          <p><strong>Adapt when the workload changes.</strong> For a different twelve-stop tour, call the same API again. The route changes, with a fifty four percent improvement over this starting order. These estimates do not include live traffic.</p>
          <p><strong>Make the same capability available to AI.</strong> Next, use Apizr to generate an MCP server from the same function. An assistant can use the existing calculation as a tool, rather than estimate the route itself.</p>
          <p><strong>Turn a business request into an action.</strong> Ask Ollama to add the Pantheon while keeping the existing stops. Our local interface passes the generated tool definition to the model, then forwards its chosen call through MCP.</p>
          <p><strong>The same logic serves another channel.</strong> The tool returns a thirteen-stop tour. The map updates from that result. The application and the assistant now use the same underlying business logic.</p>
          <p><strong>Existing expertise. New applications.</strong> Inspect your Python. Choose what to expose. Generate REST and MCP interfaces with Apizr. Bring existing expertise into your applications and AI workflows.</p>
        </div>
      </details>
    </div>
  </section>

## Choose what becomes public

<span id="discover-understand-assess"></span>
<span id="select-expose"></span>

Apizr scans code without executing it. **Readiness** is its assessment of whether
the available evidence supports an interface. Your **exposure policy** explicitly
selects the public functions: ready does not mean exposed.

A **bundle** contains the generated server, its contracts and the source needed
by the selected functions. Support helpers can be included without becoming
public. Start with [MCP tools](getting-started/quickstart.md#generate-the-mcp-bundle)
or [REST endpoints](getting-started/quickstart.md#use-rest-instead), then explore
[selection and policies](getting-started/user-guide/exposure.md).

## Decide how calls execute

<span id="execute-with-an-explicit-boundary"></span>

Generating a bundle is static analysis. Running that bundle executes your code.
Use trusted source and dependencies. The Quickstart uses **direct** mode: functions
run inside the server process, and no Docker is needed.

For **governed** execution, an **execution policy** chooses a fresh process or
container per call and the required limits. Local workers provide bounds and
cleanup, but do not isolate files or network access. OCI adds reviewed container
controls, not a VM or an untrusted-code guarantee. See
[execution boundaries](architecture/governed-repository-runtime.md) and the
[optional strict OCI profile](architecture/subprocess-deny.md).

## Find the right server and guide

The **generated MCP server** serves your selected Python functions. The separate
**[Apizr analysis MCP server](reference/apizr-mcp-server.md)**, in development 0.4,
lets a client inspect repositories and prepare exposure plans without executing
project code.

- [The full journey](getting-started/introduction.md): understand each stage and use your own code.
- [REST](getting-started/user-guide/rest.md) and [MCP](getting-started/user-guide/mcp.md): modern single-source workflows.
- [Legacy pipeline — compatibility](getting-started/user-guide/apizr.md): the historical notebook/script pipeline.
- [0.3.0 release notes](releases/0.3.0.md), [0.2.1 notes](releases/0.2.1.md) and [compatibility](getting-started/developer-guide/releases.md).
