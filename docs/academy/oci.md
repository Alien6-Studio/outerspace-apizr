---
title: Package a service for another machine
description: Distinguish a generated bundle, a built image and a published image.
lesson: 5
---

<p class="apizr-academy-kicker">Build a service · Lesson 05 · Plan about 30 min</p>

# Package a service for another machine

Your local MCP call works. Another person needs to run the service without reconstructing your shell session. A container image can package a service runtime, but merely producing an image is not the same as publishing or operating it.

Follow the existing shop service through these boundaries. Keep the generated interface selection and the runtime’s dependencies visible.

!!! abstract "By the end of this lesson"
    - Identify the bundle and runtime dependencies entering an image build.
    - Separate local image construction from registry publication.
    - Explain which evidence is needed before handing over a runnable image.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=_PwRZeBN1fM" data-apizr-video="_PwRZeBN1fM" data-apizr-title="Build an OCI image and call its MCP tool with Ollama" aria-label="Play: Build an OCI image and call its MCP tool with Ollama">
    <img src="../../assets/videos/tutorial-oci.jpg" width="480" height="360" loading="lazy" alt="Academy Part V: build an OCI service image" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

English · 8:21 · The written steps below target 0.4.6 development; the recording keeps its original demonstrated version.

## 1. Name the thing you are moving

| Item | What it contains or identifies | What it does not establish |
| --- | --- | --- |
| Exposure bundle | Selected adapters, application sources and a requirements description | An installed runtime or a running service |
| Local service image | Built filesystem/runtime identified locally | Availability in another person’s registry |
| Registry digest | The published manifest identity | That a deployment is healthy or correctly authorized |

The official OCI plugin builds service images from reviewed direct exposure bundles. It is a separately installed extension; the minimal Apizr core does not silently install Docker or your application’s dependencies.

## 2. Follow the current build recipe

Use the [OCI service guide](../reference/oci-service-plugin.md) with the MCP bundle from lesson 4. Prepare the plugin and the runtime wheel lock for the actual target platform. Keep the selected wheel versions and hashes with your exercise notes.

Read the proposed build operation and its operator grant before invoking it. Build the local service image and record the returned image identity. The video continues to a real local Ollama tool call; an AI account is not a prerequisite for understanding the build boundary.

For this exercise, a local build is sufficient. A registry push is a separate deliberate operation with an exact destination and its own authorization.

## Practice

1. Identify the source bundle, target platform and runtime wheel lock used for your image.
2. Build locally following the guide. Record the resulting image identity.
3. A colleague says, “The build succeeded, so the image is available in our production registry.” Name the missing operation and the evidence you would check after it. Do not publish an image merely to answer the question.

??? success "Check your reasoning"

    The missing operation is a deliberate registry push. Confirm the expected destination and the returned registry manifest digest, rather than treating a local image ID as that registry identity.

    A subsequent deployment needs its own runtime, access controls and health checks. A build receipt or a successful tool call may support those reviews, but neither establishes all operational or security properties of the resulting service.

[Back to the Academy](index.md) · [Continue to the next lesson](experiment-inspection.md)
