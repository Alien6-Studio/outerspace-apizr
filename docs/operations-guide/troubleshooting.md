# Diagnose an environment or service failure

Use a specific symptom, check the relevant boundary, correct its real inputs and
verify the result. Keep credentials and business payloads out of shared logs.

## Before you begin

Record Apizr/Python versions, the command's stable diagnostic code and the relevant
bundle/image digest. Keep exact inputs for private review. Use a local health check
and one harmless known request before testing a service with real business data.

| Symptom | Verification | Correction | Control after correction |
| --- | --- | --- | --- |
| Run cannot import pandas | Check the interpreter behind `apizr` | Install workload requirements there, or use its existing environment | Successful Run with expected observed package versions |
| Source read denied | Compare canonical root with `source.analyze` grant | Review a grant for that exact root | Same analysis command succeeds |
| Installed plugin not available | `plugins list --active --json` with the chosen store | Enable the reviewed installed version | Inventory identifies that exact version |
| Missing operator build/push rights | Check operation/target/plugin identities | Grant only required rights for those exact inputs | Managed invocation passes admission then verifies result |
| Port is occupied | Check owned process/port with host tooling | Select a free port consistently | Health plus business request succeeds |
| Health passes, business call fails | Check service logs privately and generated application pins/resources | Prepare missing runtime inputs; regenerate if bytes changed | Real REST/MCP business response matches |
| Bundle integrity failure | Compare retained manifest/artifact bytes | Restore reviewed bytes or generate a new bundle | Startup checks and business call pass |
| Docker/image unavailable | Explicit socket and immutable image/platform | Prepare the trusted required image/backend | Startup and real container call succeed |
| TLS/auth push refusal | Exact repository, CA and dedicated credential file | Correct that reviewed TLS/auth configuration | Immutable remote observation confirmed |
| Attest proof refusal | Independently selected signer/trust/TSA and exact delivery | Correct legitimate trust/input mismatch; preserve altered proof | Native verification passes original and refuses altered proof |
| Interrupted delivery | Saved per-destination observation and exact request | Supported `delivery resume` for that saved request | Result state confirms each target; unknown remains unknown |
| Experiment store corrupt | Query the whole copied store | Preserve failure and restore a verified quiescent backup separately | `experiment list --store` validates every record |

## Interpret failure scope

Static eligibility, tool input validation, business refusal and runtime failure
are different. The [user troubleshooting guide](../user-guide/troubleshooting.md)
shows input-shape versus stock errors. The [research example](../examples/research-serving.md)
shows why a required helper can block a selection while an unrelated unfinished
experiment does not.

## Preserve evidence before recovery

Do not globally prune Docker, delete store records or widen all grants to see
whether a command works. Stop only processes/containers you own and retain the
specific failure artifact. A failed transfer does not imply a remote rollback.
Run your host/platform's authenticated deployment procedure if returning to a
known image; no native Apizr service rollback command is promised.

Continue with the exact [command and error references](../reference/index.md).
