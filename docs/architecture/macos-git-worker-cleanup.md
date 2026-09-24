# macOS Git and worker cleanup investigation

Investigation for [#130](https://github.com/Alien6-Studio/outerspace-apizr/issues/130),
starting at master `b368c5b`, after the two failures in
[run 35981726530](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/35981726530).
The fixes address separate mechanisms and are committed separately.

## Evidence and historical limits

The SSH assertion retains `git_cleanup_failed`, but not the underlying syscall
or errno. The worker assertion retains a missing descendant marker, but not its
invocation result. Those historical values cannot be reconstructed from the logs.
A fixed exploratory series of 25 original scenarios on each of macOS/Python 3.11
and 3.14 passed: this does not resolve either failure or establish its cause.
The controlled real-process regressions below demonstrate reproducible failure
mechanisms. Their exact correspondence to the historical jobs is a diagnostic
uncertainty, not an outstanding defect. #130 is closed after #131 and successful
post-merge validation on master. The earlier green checks on #129 are not evidence for
this correction.

## Git: zombie-only group before its first signal

A test-owned helper in a separate process group retains an ordinary group member
as an unreaped child. That member exits naturally with status 23, before the
leader exits with status 128. A handshake and `ps` confirm its zombie state,
parent and group IDs. No earlier SIGKILL has succeeded.

On macOS, the first `killpg(group, SIGKILL)` then returns **EPERM (errno 1)**.
The leader is already reaped; reaping it again cannot reap the helper's child.
The original loop/finalizer makes three immediate calls, all denied while the
zombie remains. The original runner reproduces `git_cleanup_failed`. This differs
from #125, which concerned a redundant signal *after* successful group signalling.
GitRunner already remembered successful signals before this fix.

The regression deliberately retains the zombie across those three calls and
then acknowledges its reaping. The corrected runner confirms **ESRCH (errno 3)**
and reports the original `git_command_failed`. It does not suppress EPERM.
A second case retains the zombie for the whole cleanup budget: on macOS it must
still report `git_cleanup_failed`. On Linux, `killpg` can succeed for a zombie-only
group; the same cases exercise that kernel behavior without skips.

The correction polls only an EPERM outcome, within the **existing two-second
cleanup budget**, shared by signalling and direct-child reaping. The 20 ms polling
interval matches the runner's existing I/O poll interval: it lets an independent
parent/init perform reaping, rather than treating an immediate retry as proof.
Only a successful group signal or ESRCH confirms cleanup. A permanent denial or
unconfirmed wait still fails. There is no new overall budget, process-list scan
in production, blanket PermissionError exception, or change to SSH trust rules.
Output bounds, stream closure, cancellation and detached-descendant limits remain.

`tests/git_source/test_cleanup.py` records syscall results, errno, process state,
leader return code and the helper's acknowledged wait status in JUnit properties.
It also checks streams, direct-child reaping and a fresh successful invocation.
The original real-SSH unknown/changed/revoked-key assertions remain unchanged and
are included in the repetition suite.

## Worker: preparation is not guaranteed before the invocation deadline

A separate real-process regression suspends the worker immediately before its
module import. With the original **1,200 ms** policy, the invocation returns
`timeout`; the recorded process state is `T`, it is killed with SIGKILL and reaped,
and its streams close. The source has not run and no descendant marker exists.
The next normal repository invocation succeeds. This establishes that absence of
the marker alone cannot identify a production cleanup failure.

The original cleanup fixture unconditionally read that marker *before* checking
the result, and its emergency cleanup started only after the read. Its startup
assumption and teardown gap are fixed in the fixture, not the supervisor.

The replacement uses a bounded socket/pipe handshake. The descendant atomically
records its identity, creates its heartbeat and reports readiness. The host
checks that it is live in the worker's group, then explicitly permits the worker
to complete. It asserts a successful invocation, terminal descendant state,
closed streams and direct-child reaping. The ordinary five-second invocation
policy is a preparation guard; no short wall timeout is used as a synchronization
primitive. The production deadline still includes startup, as the unchanged
1,200 ms delayed-start regression demonstrates. Existing timeout tests keep
their limits. This is not an increase in a production timeout.

Emergency teardown encloses preparation as well as assertions. A deliberate
handshake failure verifies this path and recovery. Both the single-source and
repository-worker cleanup tests reuse the synchronized fixture. No fixed
post-exit sleep is used as evidence of termination.

## Fixed validation series

```sh
uv run --locked python scripts/repeat_extension_cleanup.py \
  --suite git-worker --repetitions 25 --output /tmp/git-worker-cleanup-evidence
```

Each iteration must execute all nine cases successfully, with no missing or
skipped test. All 25 iterations run even after a failure. The output directory
must be new: previous logs cannot be overwritten. Every log, JUnit report,
syscall/process observation and JSON summary is retained. The added CI matrix
runs this series on macOS and Linux, with Python 3.11 and 3.14, and uploads its
artifacts even on failure. The existing extension-cleanup series is preserved.

The standard suite, coverage gates, security mutations and installed-wheel SSH
proof remain required. See the linked PR for final counts and CI artifacts.
