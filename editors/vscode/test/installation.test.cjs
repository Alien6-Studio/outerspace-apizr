const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { requirement, installationCommand, ManagedEngine } = require('../out/installation');
const spec = require('../engine.json');

test('managed installation admits only an exact official version or source commit', () => {
    assert.match(requirement(spec), /^outerspace-apizr\[notebook\] @ git\+https:\/\/github.com\/Alien6-Studio\/outerspace-apizr.git@[a-f0-9]{40}$/);
    assert.equal(requirement({ ...spec, source: { kind: 'pypi' } }), 'outerspace-apizr[notebook]==0.4.6');
    for (const source of [{kind:'git',commit:'main'}, {kind:'git',commit:'x; echo secret'}, {kind:'url',url:'https://example.com'}]) {
        assert.throws(() => requirement({...spec, source}), {code:'invalid_engine_spec'});
    }
    assert.throws(() => requirement({...spec, version:'latest'}), {code:'invalid_engine_spec'});
});

test('installer cancellation and deadlines stop processes before returning', async () => {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'apizr-installer-process-'));
    try {
        const marker = path.join(root, 'should-not-exist');
        const controller = new AbortController();
        const work = installationCommand(process.execPath, ['-e', `setTimeout(()=>require('node:fs').writeFileSync(${JSON.stringify(marker)},'bad'),1000);setInterval(()=>{},1000)`], root, process.env, controller.signal);
        setTimeout(() => controller.abort(), 100);
        await assert.rejects(work, {code:'cancelled'});
        await assert.rejects(installationCommand(process.execPath, ['-e','setInterval(()=>{},1000)'], root, process.env, new AbortController().signal, 50), {code:'installation_timeout'});
        await assert.rejects(installationCommand(process.execPath, ['-e',"process.stdout.write('x'.repeat(1100000));setInterval(()=>{},1000)"], root, process.env, new AbortController().signal), {code:'installation_output_limit'});
        await new Promise(resolve => setTimeout(resolve, 1000));
        await assert.rejects(fs.access(marker), {code:'ENOENT'});
    } finally { await fs.rm(root, {recursive:true,force:true}); }
});

test('managed environments are reused only for the bundled source identity and contained directory', async () => {
    const root = await fs.mkdtemp(path.join(os.tmpdir(), 'apizr-installer-state-'));
    try {
        const engine = new ManagedEngine(root, spec, process.env);
        const directory = 'engine-test';
        await fs.mkdir(path.join(root,directory,'bin'), {recursive:true});
        const python = path.join(root,directory,'bin','python');
        await fs.writeFile(python,'not executed', {mode:0o700});
        const identity = crypto.createHash('sha256').update(requirement(spec)).digest('hex');
        for (const marker of [{identity:'wrong',directory},{identity,directory:'../outside'}]) {
            await fs.writeFile(path.join(root,'engine.json'),JSON.stringify(marker));
            assert.equal(await engine.installed(),undefined);
        }
        await fs.writeFile(path.join(root,'engine.json'),JSON.stringify({identity,directory}));
        assert.equal((await engine.installed()).command,python);
        assert.deepEqual(await engine.install(()=>assert.fail('A reused engine needs no preparation'),new AbortController().signal), await engine.installed());
        const cancelled = new AbortController();cancelled.abort();
        await assert.rejects(engine.install(()=>{},cancelled.signal),{code:'cancelled'});
    } finally { await fs.rm(root,{recursive:true,force:true}); }
});
