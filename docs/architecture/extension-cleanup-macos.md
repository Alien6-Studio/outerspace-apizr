# macOS extension cleanup diagnosis

Investigation for [#124](https://github.com/Alien6-Studio/outerspace-apizr/issues/124),
2026-09-24, starting from master `3d5336d`. This change is independent of #123.

## Evidence and its limits

[Job 107301930630](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/35896591658/job/107301930630)
failed in `_cleanup` with the direct child already reaped (`returncode=0`). Its
log does **not** retain the original system-call error, so that historical errno
cannot be recovered. Passing runs, including #123, do not establish a fix.

A fixed exploratory series of 100 original scenarios passed on local macOS with
Python 3.11.14; another 100 passed with Python 3.14.7. Those observations alone
did not reproduce or resolve the failure. A synchronized real-process fixture
then reproduced `CleanupFailed` on **both interpreters before the runtime change**:

1. A live ordinary descendant belongs to the extension's process group and holds
   the output streams; a FIFO handshake allows the leader to exit.
2. `_exchange` reaps the leader and `killpg(group, SIGKILL)` returns success.
3. The descendant closes its descriptors and becomes a zombie. A test-owned
   parent outside the target group postpones `waitpid` until an explicit release,
   removing the race with launchd/init reaping. `ps` confirms state `Z`, its PGID
   and its still-living parent's PID.
4. `_cleanup` sends SIGKILL again. Both this call and its existing retry return
   `EPERM` (errno 1), although the earlier group signal succeeded. Cleanup reports
   failure. The test parent subsequently reaps the descendant with SIGKILL status.

This is a demonstrated supervisor failure mechanism, not a failing assertion
caused by an observation delay in the original test. The held zombie makes the
otherwise transient process state deterministic; the original CI log cannot
prove that its unrecorded errno was identical.

The [XNU `killpg1` implementation](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/kern_sig.c#L1580)
filters zombie members from group iteration and returns POSIX `EPERM` when no
signalable member is found in an existing group. This explains the observed
second-signal result; `EPERM` in general still means cleanup cannot be confirmed.

## Minimal correction

The invocation records successful group signalling from `_exchange` and passes
that fact to `_cleanup`, even if the exchange later fails or is cancelled.
Final cleanup only sends a group signal when one has not already succeeded.
The flag is set after the system call succeeds (or the existing `ESRCH` handling
confirms no group), never merely because the leader exited.

Stream closure, the direct-child wait and its existing deadline always remain.
No syscall failure is globally ignored, and `CleanupFailed` is retained for
unconfirmed signalling or reaping. There are no new production sleeps, larger
time budgets, process-list scans or dependencies. Other worker supervisors are
unchanged. Successful SIGKILL delivery is not a claim that detached descendants
or uninterruptible kernel tasks have been contained; the existing
[trust boundary](../reference/extension-invocation.md#cleanup-and-trust-boundary)
continues to apply.

## Reproducible validation

The synchronized regression covers success, nonzero plugin exit and explicit
cancellation while a test-owned detached helper holds a pipe. Each case checks
closed host streams, direct-child reaping, the ordinary descendant's terminal
state and SIGKILL wait status, helper teardown, and a successful next invocation.
A separate negative case keeps `CleanupFailed` for denied group signals.

```sh
uv run --locked pytest tests/extension_runtime
uv run --locked python scripts/repeat_extension_cleanup.py \
  --repetitions 25 --output /tmp/extension-cleanup-evidence
```

The fixed series runs all 25 iterations, including after a failure, with no
retry-until-success rule. Every iteration must pass all seven selected cases,
without skips. JSON summaries and each iteration's log/JUnit (including syscall
and process-state properties) are retained. The dedicated workflow runs the same
series on macOS and Linux with Python 3.11 and 3.14 and uploads all results even
when a job fails. Ordinary compatibility, packaging, security and coverage gates
remain unchanged.
