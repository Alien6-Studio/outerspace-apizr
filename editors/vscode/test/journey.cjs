const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vscode = require('vscode');
const { parseJson, stringify } = require('../out/json');

exports.run = async () => {
    const root = process.env.APIZR_VSCODE_PROOF;
    try {
        const fixture = parseJson(fs.readFileSync(path.join(root, 'fixtures.json'), 'utf8'));
        const extension = vscode.extensions.getExtension('alien6-studio.apizr');
        assert.ok(extension, 'The installed candidate VSIX must be loaded');
        const api = await extension.activate();
        const project = vscode.Uri.file(fixture.project);
        const history = await api.refreshRuns(project);
        assert.ok(history.ok, stringify(history));
        assert.deepEqual(history.value, fixture.history);
        assert.equal(history.value.total, 3);
        assert.deepEqual(history.value.runs.map(run => run.status).sort(), ['failed', 'success', 'success']);
        for (const [id, expected] of Object.entries(fixture.records)) {
            const shown = await api.showRun(id, project);
            assert.ok(shown.ok, stringify(shown));
            assert.deepEqual(shown.value, expected);
            assert.equal(vscode.window.activeTextEditor.document.getText(), stringify(expected, 2));
        }
        const compared = await api.compare(...fixture.comparison_ids, project);
        assert.ok(compared.ok, stringify(compared));
        assert.deepEqual(compared.value, fixture.diff);
        fs.writeFileSync(path.join(root, 'proof.json'), JSON.stringify({
            result: 'pass', vscode: vscode.version, outside_checkout: fixture.outside_checkout,
            run_digests: Object.keys(fixture.records),
            cases: ['same-three-jupyter-runs', 'success-and-failure-statuses', 'canonical-show-and-diff'],
        }, null, 2) + '\n');
    } catch (error) {
        fs.writeFileSync(path.join(root, 'proof.json'), JSON.stringify({ result: 'failure', message: String(error.message).slice(0, 4096) }));
        throw error;
    }
};
