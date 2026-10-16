"""Temporary Python audit instrumentation for explicitly selected qualification venvs."""

import json
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def guarded_engine(python: Path, log: Path):
    """Deny and count Python DNS/INET operations even in isolated child interpreters.

    This instruments a trusted workload, not hostile native code or VS Code's own
    Electron services. Only two uniquely named files in the selected venv are
    installed; both are removed on exit. Existing environment files are untouched.
    """
    info = json.loads(
        subprocess.check_output(
            [
                str(python),
                "-I",
                "-B",
                "-c",
                "import json,sys,sysconfig;print(json.dumps([sys.prefix,sys.base_prefix,sysconfig.get_path('purelib')]))",
            ],
            text=True,
            timeout=30,
        )
    )
    prefix, base, site = map(Path, info)
    assert prefix != base and site.is_relative_to(prefix), (
        "Select a disposable virtualenv"
    )
    name = "_apizr_qualification_network_" + uuid.uuid4().hex
    module, hook = site / (name + ".py"), site / (name + ".pth")
    assert not module.exists() and not hook.exists() and not log.exists()
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("")
    source = """import json, os, socket, sys
LOG = %r
ENGINE = False
def record(kind, event):
    with open(LOG, "a") as stream:
        stream.write(json.dumps({"pid": os.getpid(), "kind": kind, "event": event}) + "\\n")
def audit(event, args):
    global ENGINE
    if not ENGINE and (event == "cpython.run_module" and str(args[0]).startswith("apizr") or event == "import" and str(args[0]).startswith("apizr")):
        ENGINE = True
        record("engine", "apizr")
    if event == "socket.getaddrinfo" or event == "socket.gethostbyname" or event == "socket.gethostbyaddr" or (event in {"socket.connect", "socket.bind", "socket.sendto"} and args[0].family in {socket.AF_INET, socket.AF_INET6}):
        record("attempt", event)
        raise PermissionError("qualification_network_denied")
sys.addaudithook(audit)
record("started", "guard")
""" % str(log)
    try:
        module.write_text(source)
        hook.write_text("import " + name + "\n")
        # Exercise real DNS and loopback connections as positive controls. The
        # measured phase starts only after both have been observed and denied.
        subprocess.run(
            [
                str(python),
                "-I",
                "-B",
                "-c",
                """import socket
def connect():
    with socket.socket() as client: client.connect(("127.0.0.1", 1))
for operation in (lambda: socket.getaddrinfo("127.0.0.1", 1), connect):
    try: operation()
    except PermissionError as error: assert str(error) == "qualification_network_denied"
    else: raise AssertionError("missing network guard")
""",
            ],
            check=True,
            timeout=30,
        )
        positive = [json.loads(line) for line in log.read_text().splitlines()]
        assert {r["event"] for r in positive if r["kind"] == "attempt"} == {
            "socket.getaddrinfo",
            "socket.connect",
        }
        log.write_text("")
        result = {}
        yield result
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        attempts = [r for r in rows if r["kind"] == "attempt"]
        result.update(
            positive_controls=2,
            connection_attempts=len(attempts),
            guarded_processes=len({r["pid"] for r in rows if r["kind"] == "started"}),
            apizr_processes=len({r["pid"] for r in rows if r["kind"] == "engine"}),
        )
        assert not attempts, "Qualification workload attempted Python network access"
    finally:
        hook.unlink(missing_ok=True)
        module.unlink(missing_ok=True)
        for compiled in (site / "__pycache__").glob(name + ".*.pyc"):
            compiled.unlink()
