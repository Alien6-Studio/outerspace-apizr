"""Hold a naturally exited group member until the host explicitly reaps it."""

import os
import select
import signal
import socket

from extension_runtime.held_group import receive, send


def hold(address):
    group = os.getpgrp()
    os.setpgid(0, 0)
    ready_r, ready_w = os.pipe()
    exit_r, exit_w = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(ready_r)
        os.close(exit_w)
        os.setpgid(0, group)
        os.write(ready_w, b"ready")
        os.close(ready_w)
        assert select.select([exit_r], [], [], 10)[0]
        os.read(exit_r, 1)
        os._exit(23)
    os.close(ready_w)
    os.close(exit_r)
    channel = socket.socket(socket.AF_UNIX)
    reaped = False
    try:
        assert select.select([ready_r], [], [], 5)[0]
        assert os.read(ready_r, 5) == b"ready"
        os.close(ready_r)
        os.close(0)
        os.close(1)
        os.close(2)
        channel.connect(address)
        send(channel, {"helper": os.getpid(), "child": child, "group": group})
        assert receive(channel) == "exit-child"
        os.write(exit_w, b"x")
        send(channel, {"event": "released"})
        assert receive(channel) == "reap"
        pid, status = os.waitpid(child, 0)
        reaped = True
        send(channel, {"event": "reaped", "pid": pid, "status": status})
    finally:
        if not reaped:
            pid, _ = os.waitpid(child, os.WNOHANG)
            if not pid:
                os.kill(child, signal.SIGKILL)
                os.waitpid(child, 0)
        os.close(exit_w)
        channel.close()
    os._exit(0)
