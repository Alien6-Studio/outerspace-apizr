---
template: home.html
title: Python to REST APIs and MCP servers
description: Turn Python code and notebooks into REST APIs and MCP tools with Apizr. Open source, with practical guides and video tutorials to get you started.
---

<div class="apizr-home-intro" markdown="1">

<span id="apizr"></span>

# Turn Python code into REST APIs and MCP tools

Make your Python functions available to applications and AI assistants.
Apizr reads your code, lets you choose what to share, and generates a REST API
or an MCP server. Your business logic stays in Python.

MCP (Model Context Protocol) lets AI assistants discover and use tools.

**[Apizr 0.4.4](releases/0.4.4.md) is available.** Python 3.11–3.14 · Open source,
GPL-3.0-or-later.

<div class="apizr-home-actions" markdown="1">

[Quickstart: MCP and REST calls](getting-started/quickstart.md){ .md-button .md-button--primary }
[Install Apizr](getting-started/install.md){ .md-button }

</div>

</div>

Start with two Python functions and make your first calls in the
[Quickstart](getting-started/quickstart.md). The core is enough: no plugin,
Docker or AI account is needed for its REST and Python MCP examples.

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

## Choose your next step

- **[Make your first calls](getting-started/quickstart.md)** — turn Python functions into REST endpoints or MCP tools.
- **[Explore a project with an AI assistant](reference/apizr-mcp-server.md)** — use Apizr's optional analysis plugin.
- **[Package a service for deployment](reference/oci-service-plugin.md)** — build a container image and publish it to your registry.

See the [installation guide](getting-started/install.md) for package availability
and optional plugins.

## Choose what becomes public

<span id="discover-understand-assess"></span>
<span id="select-expose"></span>

Apizr scans code without executing it and tells you which functions it can turn
into an interface. You choose which ones become public. Their private helpers
can be included without becoming endpoints or tools.

The generated **bundle** contains the server, its API or tool definitions and the
source it needs. Start with [REST endpoints](getting-started/quickstart.md#use-rest-instead)
or [MCP tools](getting-started/quickstart.md#generate-the-mcp-bundle), then use
[your own repository](getting-started/onboarding.md).

## Decide how calls execute

<span id="execute-with-an-explicit-boundary"></span>

The Quickstart runs trusted functions inside the generated server. For fresh
workers, timeouts or container execution, continue with
[execution policies](getting-started/user-guide/execute.md). Running a generated
server executes your Python code; static analysis does not make unfamiliar code
safe to run.

<span id="find-the-right-server-and-guide"></span>

## Explore the MCP ecosystem

Find Apizr's analysis plugin on
[Glama](https://glama.ai/mcp/servers/Alien6-Studio/outerspace-apizr) and the
[official MCP Registry](https://registry.modelcontextprotocol.io/?q=io.github.Alien6-Studio%2Fouterspace-apizr).
It helps an assistant explore your project. To let an assistant call your own
functions, follow the [MCP guide](getting-started/user-guide/mcp.md).

Watch the tutorials throughout these guides or visit
[Alien6 Studio on YouTube](https://www.youtube.com/@Alien6Studio).

Want to improve Apizr? The [contributor guide](about/CONTRIBUTING.md) covers
development setup, tests and pull requests.
