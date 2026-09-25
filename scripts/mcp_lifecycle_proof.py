"""Installed stdio/process lifecycle proof with a synchronized, blocked test worker.

Only this test bootstrap replaces compiler work. The shipped server, official SDK,
real extension runtime and its subprocess cleanup remain in use without changes.
"""

import json
import os
import signal
import sys
from pathlib import Path

import anyio
import mcp.client.stdio as transport
from mcp import Client, StdioServerParameters


async def appeared(path: Path):
    with anyio.fail_after(10):
        while not path.exists():
            await anyio.sleep(0.01)


def stopped(path: Path):
    pid = int(path.read_text())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    raise AssertionError(f"calculation {pid} survived cleanup")


def fixtures(root: Path, config: dict):
    directory = root / "lifecycle"
    directory.mkdir()
    worker = directory / "blocked-worker"
    worker.write_text(
        f"#!{config['plugin_python']}\n"
        "import os, signal, sys\nfrom pathlib import Path\n"
        "sys.stdin.buffer.read()\n"
        "assert 'APIZR_TEST_SECRET' not in os.environ\n"
        f"Path({str(directory / 'worker.pid')!r}).write_text(str(os.getpid()))\n"
        "signal.pause()\n"
    )
    worker.chmod(0o700)
    bootstrap = directory / "server.py"
    bootstrap.write_text(
        "import sys\nfrom pathlib import Path\nfrom apizr_mcp import server\n"
        f"directory = Path({str(directory)!r})\n"
        "original = server.invoke_extension\n"
        "async_original = server.Calculations.call\n"
        "def invoke(python, module, operation, arguments, **kwargs):\n"
        "    if (directory / 'block').exists():\n"
        "        python = directory / 'blocked-worker'\n"
        "    return original(python, module, operation, arguments, **kwargs)\n"
        "async def call(self, operation, arguments):\n"
        "    try:\n"
        "        return await async_original(self, operation, arguments)\n"
        "    finally:\n"
        "        (directory / 'cleaned').touch()\n"
        "server.invoke_extension = invoke\n"
        "server.Calculations.call = call\n"
        "raise SystemExit(server.main(sys.argv[1:]))\n"
    )
    return directory, bootstrap


async def exercise(root: Path):
    config = json.loads((root / "installed.json").read_text())
    directory, bootstrap = fixtures(root, config)
    spawned = []
    original_spawn = transport._create_platform_compatible_process

    async def spawn(**kwargs):
        process = await original_spawn(**kwargs)
        spawned.append(process)
        return process

    transport._create_platform_compatible_process = spawn
    target = StdioServerParameters(
        command=config["plugin_python"],
        args=["-I", "-B", str(bootstrap), "--project", config["project"]],
        env={"APIZR_TEST_SECRET": "must-not-be-inherited"},
        cwd=root,
    )

    def arm():
        for name in ("worker.pid", "cleaned"):
            (directory / name).unlink(missing_ok=True)
        (directory / "block").touch()

    async def confirm():
        await appeared(directory / "cleaned")
        stopped(directory / "worker.pid")
        (directory / "block").unlink()

    try:
        for mode in ("auto", "legacy"):
            arm()
            timed = target.model_copy(
                update={"args": [*target.args, "--timeout-ms", "5000"]}
            )
            async with Client(timed, mode=mode, read_timeout_seconds=15) as client:
                result = await client.call_tool("apizr_analyze", {})
                assert result.structured_content["error"]["code"] == "timeout"
                await confirm()
                assert not (await client.call_tool("apizr_analyze", {})).is_error
            print(f"PASS {mode}: actual calculation timeout, reaping, next call")

            arm()
            async with Client(target, mode=mode, read_timeout_seconds=15) as client:
                cancellation = anyio.CancelScope()

                async def call(cancellation=cancellation):
                    with cancellation:
                        await client.call_tool("apizr_analyze", {})

                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(call)
                    await appeared(directory / "worker.pid")
                    assert len((await client.list_tools()).tools) == 3
                    busy = await client.call_tool("apizr_readiness", {})
                    assert busy.structured_content["error"]["code"] == "server_busy"
                    cancellation.cancel()
                await confirm()
                assert not (await client.call_tool("apizr_analyze", {})).is_error
            print(
                f"PASS {mode}: cancellation, responsive discovery, busy refusal, reaping, next call"
            )

            for stop in (
                "eof",
                "disconnect",
                signal.SIGTERM,
                signal.SIGINT,
                signal.SIGHUP,
            ):
                arm()
                cancel_session = anyio.CancelScope()
                errors = []
                process = None

                async def session(
                    cancel_session=cancel_session, mode=mode, errors=errors
                ):
                    with cancel_session:
                        try:
                            async with Client(
                                target, mode=mode, read_timeout_seconds=15
                            ) as client:
                                await client.call_tool("apizr_analyze", {})
                        except Exception as error:
                            errors.append(type(error).__name__)

                async with anyio.create_task_group() as tasks:
                    tasks.start_soon(session)
                    await appeared(directory / "worker.pid")
                    process = spawned[-1]
                    if stop == "eof":
                        assert process.stdin is not None
                        await process.stdin.aclose()
                    elif stop == "disconnect":
                        cancel_session.cancel()
                    else:
                        os.kill(process.pid, stop)
                    with anyio.fail_after(10):
                        await process.wait()
                await confirm()
                assert process is not None
                assert process.returncode == 0, (stop, process.returncode, errors)
                async with Client(target, mode=mode, read_timeout_seconds=15) as client:
                    assert not (await client.call_tool("apizr_analyze", {})).is_error
                print(
                    f"PASS {mode}: {stop}, server exit, calculation reaped, new session"
                )
    finally:
        transport._create_platform_compatible_process = original_spawn
        # Bounded fixture cleanup even on failed assertions; never hide failures.
        for process in spawned:
            if process.returncode is None:
                process.kill()
                with anyio.move_on_after(5, shield=True):
                    await process.wait()
        marker = directory / "worker.pid"
        if marker.exists():
            try:
                os.kill(int(marker.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


if __name__ == "__main__":
    anyio.run(exercise, Path(sys.argv[1]))
