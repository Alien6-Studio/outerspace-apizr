"""Test-process-only evidence; never embedded in artifacts or public results."""

import importlib
import json
import sys
import time


def install(root):
    # The generated standalone package lives here; this is test instrumentation,
    # not source-module loading or a production namespace compatibility shim.
    sys.path.insert(0, str(root))
    docker = importlib.import_module("apizr_governed.oci.docker")
    supervisor = importlib.import_module("apizr_governed.oci.supervisor")
    original_run = docker.DockerProvider.run
    original_exchange = supervisor.exchange
    original_execute = supervisor.execute
    original_remove = docker.DockerProvider.remove
    events = []

    def run(self, args, **kwargs):
        start = time.monotonic()
        event = {"operation": args[0]}
        try:
            raw = original_run(self, args, **kwargs)
            if args[:3] == ["inspect", "--format", "{{json .State}}"]:
                state = json.loads(raw)
                event["state"] = {
                    key: state.get(key)
                    for key in ("Running", "Status", "OOMKilled", "ExitCode")
                }
            return raw
        except Exception as error:
            event["error"] = type(error).__name__
            raise
        finally:
            event["seconds"] = time.monotonic() - start
            events.append(event)

    def exchange(*args, **kwargs):
        result = original_exchange(*args, **kwargs)
        events.append({"exchange_status": result.status})
        return result

    def remove(self, name):
        # Classification has already happened. This cannot make it pass, and
        # evidence failure must never prevent the actual cleanup attempt.
        try:
            try:
                self.run(["inspect", "--format", "{{json .State}}", name], timeout=0.25)
            except Exception as error:
                events.append({"before_remove_error": type(error).__name__})
        finally:
            original_remove(self, name)

    def execute(*args, **kwargs):
        try:
            result = original_execute(*args, **kwargs)
            events.append({"result_status": result.status})
            return result
        finally:
            with (root.parent / "observations.jsonl").open("a") as output:
                output.write(json.dumps(events) + "\n")
            events.clear()

    docker.DockerProvider.run = run
    docker.DockerProvider.remove = remove
    supervisor.exchange = exchange
    supervisor.execute = execute
