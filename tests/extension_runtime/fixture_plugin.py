"""Trusted test-only peer, copied to a disposable environment before invocation."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main():
    request = json.load(sys.stdin)
    args = request["arguments"]
    mode = args.get("mode", "ok")
    if "marker" in args:
        Path(args["marker"]).write_text(str(os.getpid()))
    response = {
        "protocol": request["protocol"],
        "request_id": request["request_id"],
        "operation": request["operation"],
        "status": "ok",
        "result": "ok",
    }
    if mode == "inspect":
        response["result"] = {
            "pid": os.getpid(),
            "cwd": os.getcwd(),
            "env": dict(os.environ),
            "arguments": args,
            "module": __name__,
            "argv": sys.argv,
        }
    elif mode == "change":
        response.update(args["change"])
    elif mode == "raw":
        os.write(1, args["raw"].encode())
        return
    elif mode == "utf8":
        os.write(1, b"\xff")
        return
    elif mode == "fail":
        print("PLUGIN-DIAGNOSTIC-SENTINEL", file=sys.stderr)
        sys.exit(7)
    elif mode == "error":
        del response["result"]
        response.update(
            status="error",
            error={"code": "private-code", "message": "PLUGIN-DIAGNOSTIC-SENTINEL"},
        )
    elif mode == "sleep":
        time.sleep(30)
    elif mode == "closed-pipes":
        os.close(1)
        os.close(2)
        time.sleep(30)
    elif mode in ("stdout", "stderr"):
        fd = 1 if mode == "stdout" else 2
        if args.get("continuous"):
            while True:
                os.write(fd, b"private-output" * 1024)
        os.write(fd, b"x" * args["count"])
    elif mode == "held-child":
        from held_group import hold

        helper = os.fork()
        if helper == 0:
            hold(args)
        # Child readiness is coordinated by the host before it lets us finish.
        ready = Path(args["leader_release"])
        with ready.open("rb", buffering=0) as channel:
            if channel.read(1) != b"x":
                raise RuntimeError("invalid leader release")
    elif mode in ("child", "child-sleep", "detached"):
        child = subprocess.Popen(
            [sys.executable, "-I", "-B", "-c", "import time; time.sleep(30)"],
            start_new_session=mode == "detached",
        )
        Path(args["child_marker"]).write_text(str(child.pid))
        if mode == "child-sleep":
            time.sleep(30)
    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
    if mode == "held-child" and args.get("fail"):
        sys.exit(7)


if __name__ == "__main__":
    main()
