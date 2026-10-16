const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const vscode = require('vscode');
const { parseJson, stringify } = require('../out/json');
async function suite() {
    const root = process.env.APIZR_VSCODE_PROOF;
    const fixture = parseJson(fs.readFileSync(path.join(root, 'fixtures.json'), 'utf8'));
    const extension = vscode.extensions.getExtension('alien6-studio.apizr');
    const originalSpawn = cp.spawn;
    let engineStarts = 0;
    const executable = vscode.workspace.getConfiguration('apizr').get('engine.executable');
    cp.spawn = function (command, ...args) { if (command === fixture.python || command === executable) engineStarts++; return originalSpawn.call(this, command, ...args); };
    assert.ok(extension, 'The real extension must be loaded');
    const api = await extension.activate();
    assert.equal(api.state().activeProcesses, 0, 'Activation cannot start an engine');
    assert.equal(engineStarts, 0, 'Activation cannot launch and finish a hidden engine process');
    const proof = { result: 'pass', vscode: vscode.version, remote: vscode.env.remoteName ?? null, node: process.version, engine: fixture.python, engine_origin: fixture.engine_origin, outside_checkout: fixture.outside_checkout, cases: [] };
    if (process.env.APIZR_VSCODE_UNTRUSTED === '1') {
        assert.equal(vscode.workspace.isTrusted, false);
        assert.equal(await vscode.commands.executeCommand('apizr.inspect', vscode.Uri.file(path.join(fixture.project, 'inspect_only.py'))), undefined);
        assert.equal(api.state().activeProcesses, 0);
        const status = await api.telemetry('preview');
        assert.equal(status.collection_enabled, false);
        assert.equal(status.transmission_available, false);
        proof.cases.push('restricted-workspace-no-engine');
    } else {
        assert.equal(vscode.workspace.isTrusted, true);
        for (const [name, expected] of Object.entries(fixture.inspections)) {
            const result = await vscode.commands.executeCommand('apizr.inspect', vscode.Uri.file(path.join(fixture.project, name)));
            assert.ok(result?.ok, stringify(result));
            assert.deepEqual(result.value, expected, name);
            if (name === 'fraud_detection.ipynb') {
                const located = result.value.locations.find(item => Number.isInteger(item.location.cell_index));
                assert.ok(located, 'Example notebook must expose real cell locations');
                await vscode.commands.executeCommand('apizr.openSource', fixture.project, located.location);
                assert.ok(vscode.window.activeTextEditor?.document.uri.scheme === 'vscode-notebook-cell');
            }
            proof.cases.push('canonical-inspection:' + name);
        }
        const uri = vscode.Uri.file(path.join(fixture.project, 'inspect_only.py'));
        await api.inspect(uri);
        const document = await vscode.workspace.openTextDocument(uri);
        const beforeEdit = engineStarts;
        const edit = new vscode.WorkspaceEdit(); edit.insert(uri, new vscode.Position(0, 0), '# unsaved edit\n');
        assert.equal(await vscode.workspace.applyEdit(edit), true);
        assert.equal(document.isDirty, true);
        assert.equal(api.state().stale, true);
        await new Promise(resolve => setTimeout(resolve, 200));
        assert.equal(engineStarts, beforeEdit, 'Typing cannot trigger inspection');
        assert.deepEqual((await api.inspect(uri)).value, fixture.inspections['inspect_only.py']);
        proof.cases.push('saved-file-and-stale-buffer');
        const beforeSave = engineStarts;
        await document.save();
        await new Promise(resolve => setTimeout(resolve, 200));
        assert.equal(engineStarts, beforeSave, 'Inspection on save must be opt-in');
        const history = await api.refreshRuns(vscode.Uri.file(fixture.project));
        assert.deepEqual(history.value, fixture.history);
        assert.deepEqual(new Set(history.value.runs.map(item => item.capture.mode)), new Set(['cli_run', 'sdk_session', 'jupyter_cell']));
        const ids = Object.keys(fixture.records);
        for (const id of ids) { assert.deepEqual((await api.showRun(id, vscode.Uri.file(fixture.project))).value, fixture.records[id]); const rendered = vscode.window.activeTextEditor.document.getText(); assert.equal(rendered, stringify(fixture.records[id], 2)); }
        assert.deepEqual((await api.compare(ids[0], ids[1], vscode.Uri.file(fixture.project))).value, fixture.diff);
        proof.cases.push('mixed-cli-sdk-jupyter-history', 'canonical-show-and-diff');
        cp.execFileSync(fixture.python, ['-I', '-B', '-c', "from pathlib import Path; from apizr import tracking\nwith tracking.session(root=Path.cwd(), source='model.py'): tracking.log_metric('score', 0.95)"], { cwd: fixture.project, env: { ...process.env, APIZR_TELEMETRY: '0' } });
        const deadline = Date.now() + 15000;
        while (api.state().history.value.total !== 4 && Date.now() < deadline) { await new Promise(resolve => setTimeout(resolve, 100)); }
        assert.equal(api.state().history.value.total, 4, 'Publication event must trigger an engine refresh');
        proof.cases.push('publication-event-refresh');
        await vscode.commands.executeCommand('apizr.telemetryEnable');
        assert.equal(api.state().telemetryAllowed, '0', 'Global VS Code opt-out overrides explicit extension opt-in');
        const report = await api.telemetry('preview');
        assert.equal(report.collection_enabled, false);
        assert.equal(report.transmission_available, false);
        assert.deepEqual(JSON.parse(report.payload).events, []);
        await vscode.commands.executeCommand('apizr.telemetryDisable');
        proof.cases.push('global-telemetry-opt-out');
        const config = vscode.workspace.getConfiguration('apizr');
        const previousMode = config.get('engine.mode');
        const previousExecutable = config.get('engine.executable');
        await config.update('engine.executable', path.join(root, 'incompatible-engine'), vscode.ConfigurationTarget.Global);
        await config.update('engine.mode', 'executable', vscode.ConfigurationTarget.Global);
        await assert.rejects(api.inspect(uri), { code: 'incompatible_engine' });
        await config.update('engine.executable', previousExecutable, vscode.ConfigurationTarget.Global);
        await config.update('engine.mode', previousMode, vscode.ConfigurationTarget.Global);
        proof.cases.push('incompatible-engine-refused');
    }
    fs.writeFileSync(path.join(root, 'proof.json'), JSON.stringify(proof, null, 2) + '\n');
    cp.spawn = originalSpawn;
}
exports.run = async () => {
    try { await suite(); }
    catch (error) {
        fs.writeFileSync(path.join(process.env.APIZR_VSCODE_PROOF, 'proof.json'), JSON.stringify({ result: 'failure', message: String(error.message).slice(0, 4096) }));
        throw error;
    }
};
