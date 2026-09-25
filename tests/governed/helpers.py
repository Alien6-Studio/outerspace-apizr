import json
import socket
import subprocess
import sys
import time
from contextlib import contextmanager

import httpx

from apizr.execution import ExecutionPolicy
from apizr.generators.mcp import generate as mcp_generate
from apizr.generators.rest import generate as rest_generate
from apizr.inspection import inspect_source

SOURCE = b"""import os
import time
state=[]
def total(a: int, /, b: int=2, *, c: int=3): return a+b+c
async def greet(name: str): return "Hello "+name
def nullable(x: int | None=None): return x
def default_null(x: int=None): return x
def counter(default: list[int]=[]):
    state.append(1)
    default.append(1)
    return [len(state),len(default)]
def environment(): return "APIZR_TEST_SECRET" in os.environ
def fail(): raise RuntimeError("database password = super-secret")
def large(n: int): return "x"*n
def loop():
    while True: pass
def sleep(): time.sleep(3600)
def crash(): os._exit(7)
def pid(): return os.getpid()
"""


def bundle(root, transport, *, policy=None, source=SOURCE, module="governed_sample"):
    (rest_generate if transport == "rest" else mcp_generate)(
        inspect_source(source, module_name=module),
        source,
        root,
        execution_policy=ExecutionPolicy() if policy is None else policy,
    )
    return root


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


# Audit in the actual transport process: worker Python starts afresh and does not
# inherit this hook. Any attempt to compile/import source in the server fails.
SERVER = """import sys,runpy
from pathlib import Path
root=Path(sys.argv[1]).resolve()
def audit(event,args):
    if event=="exec" and "/source/" in str(args[0].co_filename):
        raise RuntimeError("source executed in transport")
sys.addaudithook(audit)
if sys.argv[2]=="rest":
    import uvicorn
    app=runpy.run_path(str(root/"app.py"))["app"]
    uvicorn.run(app,host="127.0.0.1",port=int(sys.argv[3]),log_level="error")
else:
    sys.argv=[str(root/"server.py"),"--transport",sys.argv[2]]+sys.argv[3:]
    runpy.run_path(str(root/"server.py"),run_name="__main__")
"""


@contextmanager
def http_server(root, transport, *, server=SERVER):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    command = [
        sys.executable,
        "-I",
        "-c",
        server,
        str(root),
        "rest" if transport == "rest" else "streamable-http",
    ]
    command += [str(port)] if transport == "rest" else ["--port", str(port)]
    with (root / "transport.log").open("w+") as log:
        process = subprocess.Popen(command, cwd=root, stdout=log, stderr=log)
        url = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    response = httpx.get(
                        url + ("/health" if transport == "rest" else "/mcp"),
                        timeout=0.3,
                    )
                    if response.status_code < 500:
                        break
                except httpx.HTTPError:
                    pass
                if process.poll() is not None:
                    log.seek(0)
                    raise AssertionError(log.read())
                assert time.monotonic() < deadline, "server startup deadline"
                time.sleep(0.05)
            yield url, process
        finally:
            stop(process)


def manifest(root, transport):
    return json.loads((root / f"apizr-{transport}.json").read_bytes())
