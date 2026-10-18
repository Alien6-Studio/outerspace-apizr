# OCI subprocess-deny profile

The 0.3 release adds the explicit worker protocol
`apizr.subprocess-deny/v1`. In an OCI execution policy, set:

```json
{
  "schema_version": "apizr.execution/v2",
  "subprocess": {"mode": "deny"}
}
```

Use that policy with `apizr execute`, `apizr generate rest|mcp`, or
`apizr expose build rest|mcp`. Supply an immutable local image ID and its native
`linux/amd64` or `linux/arm64` platform as usual. Build a current worker using
`scripts/build_worker_image.py`; it includes the additional image label
`org.apizr.subprocess-deny.protocol=apizr.subprocess-deny/v1`. Repository execution
also requires the existing repository worker protocol label. Older images are
refused, without pulling, installing dependencies or falling back to allow mode.

The entrypoint installs an additional Linux seccomp BPF filter before importing
any project module. Docker's default seccomp and existing resource, filesystem,
network, privilege and cleanup controls remain active. The filter refuses native
`fork`, `vfork`, `clone`, `clone3`, `execve` and `execveat`, including calls issued
directly through libc. It also blocks ptrace and io_uring. Alternate syscall ABIs
terminate the worker; x32 aliases and syscall numbers at or above 512 are refused.
The implementation supports the reviewed native 64-bit little-endian x86-64 and
AArch64 syscall tables. It requires a single-threaded entrypoint and checks kernel
return values for no-new-privileges and filter installation. Failure stops startup.
Policy allowlists may not inject loader/interpreter bootstrap variables (`LD_*`,
`DYLD_*`, `PYTHON*`, `GLIBC_*`, or `GCONV_PATH`) before the filter is installed.

This strict profile also prohibits **new threads** and replacing the worker's
executable. Thread pools, multiprocessing, shell commands, external executables
and libraries that start background threads are therefore incompatible. Async
Python functions that do not start threads or child processes remain usable.
The caller can catch `PermissionError`; an uncaught application exception is
reported using the existing sanitized failure result. Kernel installation failure
is a worker failure, never successful execution with weaker controls.

This is a specific process-creation restriction for trusted-code execution, not
a general untrusted-code sandbox or a VM boundary. It relies on a trusted image,
Docker host and Linux kernel. See the [Linux seccomp documentation](https://www.kernel.org/doc/html/latest/userspace-api/seccomp_filter.html)
for filter stacking and limitations, and the [Linux syscall ABI guidance](https://man7.org/linux/man-pages/man2/seccomp.2.html).

## Compatibility and static evidence

Existing allow-mode artifacts, policies, canonical reports and backend APIs keep
their bytes and behavior. The profile is an opt-in extension, selected only by an
OCI execution policy requesting deny. Local-process execution continues to refuse
deny. The frozen Repository Readiness/Exposure v1 adapters describe the original
backend guarantees; they do not advertise this additional image protocol. Keep
`oci-container` in those policies and put the deny requirement in the separate
**execution policy**. A static `require_controls: ["subprocess_deny"]` still
refuses; no static report establishes host or worker-image availability.

Generated strict bundles contain a separate, manifest-bound bridge and use the
strict entrypoint on every invocation. Use their generated `app.py` or `server.py`.
For direct Python invocation use `apizr.subprocess_guard.single.plan/execute`, or
`apizr.subprocess_guard.repository.container_plan/execute`. The original low-level
`apizr.oci` and `apizr.repository_execution` APIs retain their allow-mode contract.

The required OCI job tests both single-source and repository execution, real
REST/MCP stdio/MCP HTTP calls, direct libc syscalls, import-time protection,
tamper refusal/recovery and cleanup. Independent positive controls verify that
ordinary allow mode can still create a process. Unit tests cover ABI dispatch,
unsupported workers and fail-closed installation; targeted mutations remove the
filter action and the worker protocol requirement to verify these checks detect
missing protection.
