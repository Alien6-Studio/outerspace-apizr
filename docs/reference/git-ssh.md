# Analyze a private Git repository through SSH

The Git adapter accepts `git@host:organization/project.git` and
`ssh://git@host:2222/organization/project.git`. Install Git and OpenSSH separately.
Prepare an SSH agent with an authorized identity and a trusted `known_hosts` file
before running Apizr. Apizr never starts an agent, adds keys, reads private keys,
or manages credentials.

## Explicit authentication

Both SSH options are required for each call. They are rejected with public HTTPS
or local sources; no implicit `SSH_AUTH_SOCK` or personal `known_hosts` is used.
An explicit remote username is required. Supply a branch, tag or full commit;
`--subdir` and the local policies behave as in the [HTTPS example](git-sources.md).
For example, after preparing the two policy files from that example:

```sh
REPOSITORY=git@github.com:organization/project.git
REF=main

apizr readiness --git "$REPOSITORY" --ref "$REF" --subdir service \
  --ssh-agent-socket "$SSH_AUTH_SOCK" --ssh-known-hosts "$HOME/.ssh/known_hosts" \
  --policy readiness.json --report
apizr expose plan --git "$REPOSITORY" --ref "$REF" --subdir service \
  --ssh-agent-socket "$SSH_AUTH_SOCK" --ssh-known-hosts "$HOME/.ssh/known_hosts" \
  --policy exposure.json --readiness-policy readiness.json --plan
apizr expose build rest --git "$REPOSITORY" --ref "$REF" --subdir service \
  --ssh-agent-socket "$SSH_AUTH_SOCK" --ssh-known-hosts "$HOME/.ssh/known_hosts" \
  --policy exposure.json --readiness-policy readiness.json --output-dir build/rest
apizr expose build mcp --git "$REPOSITORY" --ref "$REF" --subdir service \
  --ssh-agent-socket "$SSH_AUTH_SOCK" --ssh-known-hosts "$HOME/.ssh/known_hosts" \
  --policy exposure.json --readiness-policy readiness.json --output-dir build/mcp
```

Use a full commit to reproduce an analysis. Apizr resolves a branch/tag once,
prints the resolved commit to stderr and analyzes that immutable snapshot.
The repository in this example must contain a `service/calculator.py` capability
matching the example policies; substitute your own paths and selection otherwise.

## Python API

Save the example as `ssh_snapshot.py` beside the local policies and run
`python ssh_snapshot.py "$REPOSITORY" "$REF" "$SSH_AUTH_SOCK" "$HOME/.ssh/known_hosts"`.
Use fresh output directories.

```python
import sys
from pathlib import Path

from apizr.compiler import prepare_exposure, render_bundle
from apizr.exposure import ExposurePolicy
from apizr.git_source import acquire_snapshot
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_readiness import RepositoryReadinessPolicy

repository, reference, agent, known_hosts = sys.argv[1:]
with acquire_snapshot(
    repository,
    reference,
    subdir="service",
    ssh_agent_socket=Path(agent),
    ssh_known_hosts=Path(known_hosts),
) as snapshot:
    print(f"Git snapshot: commit {snapshot.commit}", file=sys.stderr)
    prepared = prepare_exposure(
        snapshot.root,
        policy=ExposurePolicy.model_validate_json(Path("exposure.json").read_bytes()),
        readiness_policy=RepositoryReadinessPolicy.model_validate_json(
            Path("readiness.json").read_bytes()
        ),
    )

# Retained sources remain usable after the private snapshot has been removed.
for interface in ("rest", "mcp"):
    write_bundle(
        Path("python-" + interface), render_bundle(prepared, interface=interface)
    )
```

The existing typed `AcquisitionLimits` and cancellation `threading.Event` also
apply to SSH. There is no fallback to HTTPS, another agent or disk identities.
`ca_file` is reserved for HTTPS and is rejected with SSH.

## Trust and isolation

OpenSSH uses only the explicitly selected agent, with disk identities,
certificates, password/interactive authentication and external key providers
disabled. Prepare an agent dedicated to the intended repository if identity
selection matters: any authorized identity already in that agent may be offered.
Agent policies requiring user confirmation may still involve the agent's own UI;
Apizr cannot control that UI, but its acquisition deadline and cancellation remain
in force. This is not an SSH sandbox or a key-management system.

Host keys must match the supplied file. Unknown, changed and revoked keys are
refused. The bounded regular file (maximum 4 MiB) is copied into acquisition's
private directory and never updated. Neither that copy, agent socket paths nor
SSH configuration is included in the exported snapshot or generated bundles.
Provide host keys verified through a trusted channel; blindly accepting a freshly
scanned key does not establish the server's identity.

`-F /dev/null` disables user and system SSH configuration. Proxy commands/jumps,
local commands, agent/X11 forwarding, tunnels and connection sharing are disabled.
Inherited `GIT_SSH`, `GIT_SSH_COMMAND`, askpass and credential variables are not
copied. Git invokes a private fixed launcher: its constant, quoted forwarding
passes argv to an isolated Python helper which execs OpenSSH. URLs and options are
never interpolated into local shell command text. OpenSSH's own filename token
expansion is avoided for user-supplied paths.

Only conventional ASCII usernames/hostnames (including bracketed IPv6) and
repository paths made of letters, digits, `_`, `.`, `-` and `/` are accepted.
Dot/parent path components, percent escapes, spaces, shell syntax and URL
credentials are refused. SCP-style addresses use port 22; `ssh://` selects an
explicit port. SSH aliases, bastions, arbitrary configuration, HTTPS credentials
and keys outside the chosen agent are not supported.

The [existing static acquisition guarantees and resource limits](git-sources.md#boundaries-and-limits)
remain unchanged, including refusals of symlinks, submodules and Git LFS.
OpenSSH additionally has a 10-second connection timeout and bounded keepalive
failure detection, within the total acquisition deadline. Killing the local
process group closes the SSH connection; Apizr cannot guarantee termination of
server-side processes or locally detached helpers.

Fixed errors include `git_ssh_options_required`, `git_ssh_options_unsupported`,
`git_ssh_not_found`, `git_ssh_agent_unavailable`,
`git_ssh_known_hosts_unavailable` and `git_ssh_known_hosts_limit`.
`git_command_failed` covers transport, host verification, authentication and
repository access failures: check the explicit agent, trusted host entry and
repository permissions. Raw SSH diagnostics and credential-bearing URLs are
never printed. CLI acquisition errors return 2; Ctrl-C cleans up and returns 130.

## Reproducible proof

Run `uv run python scripts/smoke_git_ssh.py dist/outerspace_apizr-*.whl`.
It installs the minimal wheel outside the checkout, generates dedicated fixture
keys and starts its own loopback-only OpenSSH server and agent on temporary paths.
All four commands and this Python example must match local analysis and bundles;
the trusted calculator bundle is deliberately invoked after snapshot cleanup.
No machine SSH service or personal keys are changed. The fixture needs `sshd`,
`ssh-agent`, `ssh-add` and `ssh-keygen`; these are test prerequisites, not commands
run by Apizr. Normal installation CI exercises the proof on Python 3.11 and 3.14.

See the OpenSSH documentation for [configuration precedence and authentication](https://man.openbsd.org/ssh_config)
and [the `-F` option](https://man.openbsd.org/ssh).
