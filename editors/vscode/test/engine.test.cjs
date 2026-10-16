const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { EngineClient, admitResponse } = require('../out/engine');

function fixture(code, timeoutMs = 3000) {
    const cwd = fs.mkdtempSync(path.join(os.tmpdir(), 'apizr-engine-'));
    const script = path.join(cwd, 'engine.cjs');
    fs.writeFileSync(script, code);
    const client = new EngineClient({ command: process.execPath, prefix: [script], project: '/project/apizr.toml', policy: '/operator.json', store: '.apizr/experiments/v1', cwd, timeoutMs, env: { ...process.env, APIZR_TELEMETRY_ALLOWED: '0', APIZR_TEST_CAPABILITIES: JSON.stringify(capabilities) } });
    return { client, dispose: () => { client.cancel(); fs.rmSync(cwd, { recursive: true, force: true }); } };
}
const operations = ['capabilities', 'inspect', 'experiment_list', 'experiment_show', 'experiment_diff', 'plan_exposure'];
const schemas = { capabilities: ['apizr.editor-capabilities/v1'], inspect: ['apizr.experiment-inspection/v1'], experiment_list: ['apizr.experiment-history/v1', 'apizr.experiment-history/v2'], experiment_show: ['apizr.experiment-record/v1', 'apizr.experiment-record/v2'], experiment_diff: ['apizr.experiment-diff/v1', 'apizr.experiment-diff/v2'], plan_exposure: ['apizr.exposure-plan/v1'] };
const capabilities = { schema_version: 'apizr.editor-capabilities/v1', protocol: 'apizr.editor/v1', max_request_bytes: 65536, max_response_bytes: 4194304, operations: operations.map(name => ({ name, result_schemas: schemas[name], read_only: true })) };
test('discovery and results retain canonical values and UTF-8 across chunks', async () => {
    const f = fixture(`let input=''; process.stdin.on('data', c=>input+=c); process.stdin.on('end',()=>{const r=JSON.parse(input); const value=r.operation==='capabilities'?JSON.parse(process.env.APIZR_TEST_CAPABILITIES):{schema_version:'apizr.experiment-inspection/v1', unknown:'unknown', text:'é😀'}; const b=Buffer.from(JSON.stringify({schema_version:'apizr.editor-response/v1',request_id:r.request_id,operation:r.operation,ok:true,value,diagnostics:[]})); let i=0; const send=()=>{if(i<b.length){process.stdout.write(b.subarray(i,++i));setImmediate(send);}else process.exit(0);}; send();});`);
    try { const result = await f.client.request('inspect', { source: 'model.py' }); assert.equal(result.value.text, 'é😀'); assert.equal(result.value.unknown, 'unknown'); } finally { f.dispose(); }
});
test('incompatible discovery stops before any project request', async () => {
    const f = fixture(`let input=''; process.stdin.on('data', c=>input+=c);process.stdin.on('end',()=>{const r=JSON.parse(input); if(r.operation!=='capabilities') throw Error('project touched'); process.stdout.write(JSON.stringify({schema_version:'apizr.editor-response/v1',request_id:r.request_id,operation:r.operation,ok:true,value:{schema_version:'apizr.editor-capabilities/v1',protocol:'wrong'},diagnostics:[]}));});`);
    try { await assert.rejects(f.client.request('inspect', { source: 'secret.py' }), { code: 'incompatible_engine' }); } finally { f.dispose(); }
});
for (const [name, code, expected] of [
    ['stdout bound', `process.stdout.write('x'.repeat(4194305));setInterval(()=>{},1000);`, 'response_too_large'],
    ['stderr bound', `process.stderr.write('x'.repeat(65537));setInterval(()=>{},1000);`, 'response_too_large'],
    ['deadline', `setInterval(()=>{},1000);`, 'timeout'],
    ['invalid utf8', `process.stdout.write(Buffer.from([255]));`, 'invalid_response'],
    ['failed engine', `process.stderr.write('PRIVATE TRACE');process.exit(7);`, 'engine_failed'],
]) {
    test(name, async () => {
        const f = fixture(code, name === 'deadline' ? 100 : 3000);
        try { await assert.rejects(f.client.discover(), error => error.code === expected && !error.message.includes('PRIVATE TRACE')); } finally { f.dispose(); }
    });
}
test('cancellation terminates the owned child and preserves the cancellation diagnostic', async () => {
    const f = fixture('setInterval(()=>{},1000);');
    try { const pending = f.client.discover(); setTimeout(() => f.client.cancel(), 50); await assert.rejects(pending, { code: 'cancelled' }); } finally { f.dispose(); }
});
test('abort refuses before discovery and byte limit refuses before a project request', async () => {
    const f = fixture(`let input='';process.stdin.on('data',c=>input+=c);process.stdin.on('end',()=>{const r=JSON.parse(input);assertProject=r.operation==='capabilities';if(!assertProject)throw Error('project must not run');process.stdout.write(JSON.stringify({schema_version:'apizr.editor-response/v1',request_id:r.request_id,operation:r.operation,ok:true,value:JSON.parse(process.env.APIZR_TEST_CAPABILITIES),diagnostics:[]}));});`);
    try { const c = new AbortController(); c.abort(); await assert.rejects(f.client.discover(c.signal), { code: 'cancelled' }); await assert.rejects(f.client.request('inspect', { source: 'x'.repeat(65536) }), { code: 'request_too_large' }); } finally { f.dispose(); }
});
test('envelope admits only the selected operation, request and schema', () => {
    const value = { schema_version: 'apizr.editor-response/v1', request_id: '1', operation: 'inspect', ok: true, value: { schema_version: 'apizr.experiment-inspection/v1' }, diagnostics: [] };
    assert.equal(admitResponse(JSON.stringify(value), '1', 'inspect').ok, true);
    for (const patch of [{ request_id: '2' }, { operation: 'experiment_diff' }, { extra: 'secret' }, { value: null }, { schema_version: 'v2' }]) { assert.throws(() => admitResponse(JSON.stringify({ ...value, ...patch }), '1', 'inspect'), { code: 'incompatible_engine' }); }
    assert.throws(() => admitResponse('{}\n{}', '1', 'inspect'), { code: 'invalid_response' });
});
