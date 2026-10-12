# Start, verify and stop a local service

Operate the generated quote service from its own runtime environment. You will
verify health, a business request and an invalid input, then stop it cleanly.

## Before you begin

Complete [Share a business quote](../examples/business-quote.md#generate-both-interfaces).
Open a shell in the extracted `business-quote/` directory, with sibling
`bundles/` and `runtime/`. The following commands are host procedures (venv,
Uvicorn and shell process management), not native Apizr lifecycle commands.
Starting the direct service imports trusted bundled code.

## Start and identify the process

```sh
../runtime/bin/python -m uvicorn app:app --app-dir ../bundles/rest \
  --host 127.0.0.1 --port 8000 > ../rest.log 2>&1 &
REST_PID=$!
```

Keep `REST_PID` in this shell. If the process exits, inspect the bounded relevant
log lines rather than printing business payloads or credentials into a ticket.
Choose another free local port if 8000 is occupied and use it consistently.

## Verify health and the calculation

```sh
curl --fail http://127.0.0.1:8000/health
python http_client.py http://127.0.0.1:8000 order.json
```

Health is `{"status":"ok"}`. The quote response is
`{"ok":true,"currency":"EUR","net_cents":7650,"tax_cents":1530,"total_cents":9180}`.
Check `/openapi.json`: the only business route is `/capabilities/api.quote`.
Health alone does not establish that dependencies or the model can serve a request.

```sh
curl -s -o ../invalid-response.json -w '%{http_code}\n' \
  http://127.0.0.1:8000/capabilities/api.quote \
  -H 'Content-Type: application/json' \
  -d '{"order":{"lines":[],"coupon":"none","extra":true}}'
```

Check HTTP `422`. The closed object rejects the extra field before invocation.
Use the [MCP client](../developer-guide/clients.md) for the same business contract;
its context owns and closes the stdio server process.

## Stop and confirm

```sh
kill "$REST_PID"
wait "$REST_PID" || true
```

A subsequent connection to that port should fail unless another process is using
it. Manage persistent services with your host's service manager and access policy;
Apizr does not install a daemon or invent a shared process registry.

## Update or return to a known bundle

Generate a candidate into a fresh directory and prepare its runtime separately.
Verify it on another port with both valid/invalid requests. Your host procedure
then stops/replaces the running process. Returning to a retained known bundle or
immutable image is an operator deployment procedure, not an Apizr rollback command.
See [safe regeneration](../developer-guide/regeneration.md).

When done with this disposable example, remove only its generated sibling
`bundles/`, `runtime/`, logs and extracted project after stopping owned processes.
