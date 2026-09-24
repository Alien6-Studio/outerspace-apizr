"""Test-only parent that retains a killed group member until explicitly released."""

import json
import os
import select
import signal
import socket


def receive(channel):
    channel.settimeout(5)
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = channel.recv(1)
        if not chunk or len(data) > 4096:
            raise RuntimeError("invalid test handshake")
        data.extend(chunk)
    return json.loads(data)


def send(channel, value):
    channel.sendall(json.dumps(value).encode() + b"\n")


def hold(args):
    """Run in a child of the extension, outside the extension's process group.

    Keep its ordinary group member as our unreaped child, instead of racing
    launchd/init reaping. Only the test owns this helper; runtime need not kill it.
    """
    group = os.getpgrp()
    os.setpgid(0, 0)
    read_ready, write_ready = os.pipe()
    read_live, write_live = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_ready)
        os.close(read_live)
        os.setpgid(0, group)
        os.write(write_ready, b"ready")
        os.close(write_ready)
        # Output and the liveness pipe remain open until SIGKILL.
        signal.pause()
        os._exit(90)
    os.close(write_ready)
    os.close(write_live)
    channel = socket.socket(socket.AF_UNIX)
    try:
        assert select.select([read_ready], [], [], 5)[0]
        assert os.read(read_ready, 5) == b"ready"
        os.close(read_ready)
        # Our child now owns the output streams. We must not keep them open.
        os.close(0)
        os.close(1)
        if not args.get("keep_stderr"):
            os.close(2)
        channel.connect(args["control"])
        send(
            channel,
            {"event": "ready", "helper": os.getpid(), "child": child, "group": group},
        )
        assert receive(channel) == "observe-exit"
        assert select.select([read_live], [], [], 5)[0]
        assert os.read(read_live, 1) == b""
        send(channel, {"event": "closed"})
        # The parent intentionally does not waitpid yet. The host test observes
        # the zombie and exercises cleanup before acknowledging release.
        assert receive(channel) == "reap"
        pid, status = os.waitpid(child, 0)
        send(channel, {"event": "reaped", "pid": pid, "status": status})
    finally:
        try:
            os.kill(child, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(child, 0)
        except ChildProcessError:
            pass
        os.close(read_live)
        channel.close()
    os._exit(0)
