const { test } = require('node:test');
const assert = require('node:assert/strict');
const Module = require('node:module');
const originalLoad = Module._load;
let values = {}, telemetryEnabled = true, trusted = true;
const folder = { name: 'project', uri: { scheme: 'file', fsPath: '/project' } };
const fake = { env: { get isTelemetryEnabled() { return telemetryEnabled; } }, workspace: { get isTrusted() { return trusted; }, workspaceFolders: [folder], getWorkspaceFolder: uri => uri.scheme === 'file' && uri.fsPath.startsWith('/project') ? folder : undefined, getConfiguration: section => ({ get: (key, fallback) => values[section + '.' + key] ?? fallback }) } };
Module._load = function (id, ...args) { return id === 'vscode' ? fake : originalLoad.call(this, id, ...args); };
const { childEnvironment, usageAllowed, settings, folderFor } = require('../out/environment');
Module._load = originalLoad;
test('every child inherits the stricter global and Apizr usage decision', () => {
    const saved = { ...process.env };
    try {
        delete process.env.APIZR_TELEMETRY; delete process.env.APIZR_TELEMETRY_ALLOWED; delete process.env.CI; delete process.env.APIZR_SERVED_PROCESS; delete process.env.APIZR_EXPERIMENT_RUNNER;
        process.env.PYTHONPATH = '/untrusted'; process.env.PYTHONHOME = '/untrusted';
        for (const enabled of [false, true]) for (const global of ['all', 'error', 'crash', 'off']) for (const api of [false, true]) {
            values = { 'apizr.telemetry.enabled': enabled, 'telemetry.telemetryLevel': global }; telemetryEnabled = api;
            const expected = enabled && global === 'all' && api;
            assert.equal(usageAllowed(), expected);
            const env = childEnvironment(); assert.equal(env.APIZR_TELEMETRY_ALLOWED, expected ? '1' : '0'); assert.equal(env.APIZR_TELEMETRY, expected ? '1' : '0');
            assert.equal(env.APIZR_TELEMETRY_CONTEXT, 'vscode'); assert.equal(env.PYTHONPATH, undefined); assert.equal(env.PYTHONHOME, undefined);
        }
        values = { 'apizr.telemetry.enabled': true, 'telemetry.telemetryLevel': 'all' }; telemetryEnabled = true;
        process.env.APIZR_TELEMETRY_ALLOWED = '0'; assert.equal(usageAllowed(), false);
        process.env.APIZR_TELEMETRY_ALLOWED = 'unknown'; assert.equal(usageAllowed(), false);
        delete process.env.APIZR_TELEMETRY_ALLOWED; process.env.CI = 'true'; assert.equal(usageAllowed(), false); delete process.env.CI;
        process.env.APIZR_SERVED_PROCESS = '1'; assert.equal(usageAllowed(), false); delete process.env.APIZR_SERVED_PROCESS;
        process.env.APIZR_TELEMETRY = '0'; assert.equal(usageAllowed(), false);
    } finally { process.env = saved; }
});
test('no executable is inferred and Restricted Mode refuses before launch', () => {
    values = {}; trusted = true;
    assert.throws(() => settings(folder), { code: 'engine_required' });
    values = { 'apizr.engine.mode': 'python', 'apizr.engine.python': '/engine/python', 'apizr.operatorPolicy': '/operator.json' };
    assert.deepEqual(settings(folder).prefix, ['-I', '-B', '-m', 'apizr.cli']);
    values['apizr.projectRoot'] = 'work'; assert.equal(settings(folder).cwd, '/project/work'); delete values['apizr.projectRoot'];
    values['apizr.engine.mode'] = 'executable'; values['apizr.engine.executable'] = '/tool/bin/apizr';
    assert.deepEqual(settings(folder).prefix, []);
    for (const store of ['../private', '/private', 'a//b', 'a/./b', 'a\\b', 'x:y']) { values['apizr.store'] = store; assert.throws(() => settings(folder), { code: 'invalid_store' }); }
    delete values['apizr.store']; values['apizr.timeoutMs'] = 1; assert.throws(() => settings(folder), { code: 'invalid_deadline' });
    delete values['apizr.timeoutMs']; values['apizr.operatorPolicy'] = 'relative'; assert.throws(() => settings(folder), { code: 'policy_required' });
    trusted = false; assert.throws(() => settings(folder), { code: 'workspace_untrusted' }); trusted = true;
    assert.equal(folderFor({ scheme: 'apizr-result' }), folder);
    assert.throws(() => folderFor({ scheme: 'file', fsPath: '/outside' }), { code: 'workspace_required' });
});
