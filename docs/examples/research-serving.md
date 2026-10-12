# Reuse a function from unfinished research

Share an independent prediction while unrelated experiments stay unfinished.
Then add a defect to a required helper, observe refusal and correct it legitimately.

## Expected result and prerequisites

`serving.predict(50.0)` returns REST `0.4` and MCP `{"result":0.4}`. The full audit
retains the unrelated ambiguity in `old_notebook.py`; only `serving.predict` is public.

Use [Apizr 0.4.5 core](../getting-started/install.md), Python 3.11–3.14 on Linux/macOS
and a generated REST/MCP runtime. Download
[research-serving.zip](../downloads/research-serving.zip), extract outside the
checkout and open `research-serving/`. Existing GPL-3.0-or-later files need no
scientific library or dataset: `features.py` normalizes a number, `serving.py`
uses it, `experiments.py` has a decorated generator and `old_notebook.py` imports
that unrelated ambiguous experiment.

## Authorize and build

<!-- scenario:research-build -->
```sh
python - <<'PY'
import json
from pathlib import Path
Path('operator.json').write_text(json.dumps({'schema':'apizr.operator-policy/v1',
 'grants':[{'adapter':'repository','operation':'analyze',
 'target':{'kind':'local','root':str(Path.cwd().resolve())},'permissions':['source.analyze']}]}))
Path('readiness.json').write_text('{"execution":{"modes":["direct"]}}')
PY
export RESEARCH_BUNDLES="$(cd .. && pwd -P)/research-bundles"
mkdir -p "$RESEARCH_BUNDLES"
apizr expose plan . --operator-policy operator.json --readiness-policy readiness.json \
  --interface rest --interface mcp --execution-mode direct --select python:serving:predict --plan > plan.json
apizr expose build rest . --operator-policy operator.json --readiness-policy readiness.json \
  --interface rest --execution-mode direct --select python:serving:predict --output-dir "$RESEARCH_BUNDLES/rest"
apizr expose build mcp . --operator-policy operator.json --readiness-policy readiness.json \
  --interface mcp --execution-mode direct --select python:serving:predict --output-dir "$RESEARCH_BUNDLES/mcp"
```

Contracts contain only `serving.predict`. All inspected source remains evidence;
unrelated bundled files are not imported simply because they are present.
See [selection scope](../getting-started/user-guide/exposure.md#work-with-unfinished-research-code).

## Diagnose and correct a required-helper failure

<!-- scenario:research-refusal -->
```sh
cp features.py features.original
printf '\nraise RuntimeError("unsafe required helper initialization")\n' >> features.py
if apizr expose plan . --operator-policy operator.json --readiness-policy readiness.json \
  --interface rest --execution-mode direct --select python:serving:predict > refused-plan.json 2> refusal.txt; then
  echo 'Expected required-helper refusal' >&2
  exit 1
fi
cat refusal.txt
mv features.original features.py
apizr expose plan . --operator-policy operator.json --readiness-policy readiness.json \
  --interface rest --interface mcp --execution-mode direct --select python:serving:predict --plan > corrected-plan.json
```

The diagnostic identifies the selected function's required `features` dependency.
Restoring the original legitimate helper permits the same selection. Conditional
opt-in cannot waive required helper defects.

## Verify real calls

Install both emitted requirements in a separate runtime:

<!-- scenario:research-install -->
```sh
python -m venv ../research-runtime
../research-runtime/bin/python -m pip install -r ../research-bundles/rest/requirements.txt -r ../research-bundles/mcp/requirements.txt
```

Starting these direct services executes trusted source. Run REST in one terminal:

<!-- scenario:research-serve -->
```sh
../research-runtime/bin/python -m uvicorn app:app --app-dir ../research-bundles/rest --host 127.0.0.1 --port 8000
```

From another shell in the extracted directory:

<!-- scenario:research-http -->
```sh
curl --fail http://127.0.0.1:8000/capabilities/serving.predict -H 'Content-Type: application/json' -d '{"value":50.0}'
```

Check `0.4`. Call MCP with the official SDK, without an AI account:

<!-- scenario:research-mcp -->
```sh
../research-runtime/bin/python - <<'PY'
from pathlib import Path
import anyio
from mcp import Client, StdioServerParameters
async def main():
    async with Client(StdioServerParameters(
        command=str(Path('../research-runtime/bin/python').absolute()),
        args=[str(Path('../research-bundles/mcp/server.py').resolve())])) as client:
        assert [t.name for t in (await client.list_tools()).tools] == ['serving.predict']
        result = await client.call_tool('serving.predict', {'value':50.0})
        assert not result.is_error and result.structured_content == {'result':0.4}
        print(result.structured_content)
anyio.run(main)
PY
```

Installed qualification executes these exact blocks, the helper refusal and the
restored selection. The MCP context owns and stops its server.

## Optional analysis MCP exploration

Install the `mcp` profile and configure [the analysis server](../reference/apizr-mcp-server.md)
for this exact root/policies. Request analysis/readiness summary, then detail for
`python:serving:predict`; exposure planning remains static. These analysis tools
are distinct from the generated `serving.predict` tool that executes the calculation.

## Limits and cleanup

Repository-wide integrity/resource failures still block generation. Independent
selection is not runtime safety approval. Stop owned REST processes; MCP clients
close their servers. Remove only the extracted project, generated bundles and
runtime after retaining diagnostics needed.
