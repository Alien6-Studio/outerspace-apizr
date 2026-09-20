import json
from pathlib import Path

from governed.helpers import SOURCE as BASE_SOURCE
from oci.helpers import IMAGE

from apizr.generators.mcp import generate as mcp_generate
from apizr.generators.rest import generate as rest_generate
from apizr.inspection import inspect_source
from apizr.oci.model import ExecutionPolicyV2

SOURCE = (
    BASE_SOURCE
    + b"""import socket
import subprocess
import sys
from pathlib import Path
def isolation(host: str, port: int, host_path: str):
    try:
        connection = socket.create_connection((host,port),timeout=0.2)
        connection.close()
        reachable = True
    except OSError:
        reachable = False
    Path("/tmp/scratch").write_text("ok")
    return {"reachable":reachable, "host_file":Path(host_path).exists(), "source_readable":Path(__file__).is_file(), "bundle_ro":bool(os.statvfs("/bundle").f_flag & os.ST_RDONLY), "root_ro":bool(os.statvfs("/").f_flag & os.ST_RDONLY), "scratch":Path("/tmp/scratch").read_text(), "socket":Path("/var/run/docker.sock").exists()}
def memory():
    chunks=[]
    for i in range(512): chunks.append(bytearray(1024*1024))
    return len(chunks)
def children():
    children=[]
    try:
        for i in range(40):
            children.append(subprocess.Popen([sys.executable,"-c","import time; time.sleep(20)"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
    except OSError:
        return len(children)
    finally:
        for child in children:
            child.kill()
            child.wait()
    return 40
"""
)


def bundle(root, transport, *, image=IMAGE, source=SOURCE, policy=None, select=None):
    (rest_generate if transport == "rest" else mcp_generate)(
        inspect_source(source, module_name="governed_sample"),
        source,
        root,
        execution_policy=policy or ExecutionPolicyV2(),
        runtime_image=image,
        select=select,
    )
    return root


def rehash(root: Path, transport="rest"):
    import hashlib

    from apizr.interfaces.serialization import json_bytes

    manifest_path = root / f"apizr-{transport}.json"
    manifest = json.loads(manifest_path.read_bytes())
    bridge = json.loads((root / "execution/bundle.json").read_bytes())

    def digest(path):
        return {
            "algorithm": "sha256",
            "value": hashlib.sha256((root / path).read_bytes()).hexdigest(),
        }

    for path in bridge["artifacts"]:
        bridge["artifacts"][path] = digest(path)
    (root / "execution/bundle.json").write_bytes(json_bytes(bridge))
    manifest["artifacts"] = {
        path: digest(path) for path in [*bridge["artifacts"], "execution/bundle.json"]
    }
    manifest_path.write_bytes(json_bytes(manifest))
