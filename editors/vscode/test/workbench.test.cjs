const { test } = require('node:test');
const assert = require('node:assert/strict');
const Module = require('node:module');
class Uri {
    constructor(scheme, fsPath) { this.scheme = scheme; this.fsPath = fsPath; }
    toString() { return this.scheme + ':' + this.fsPath; }
}
const script = new Uri('file', '/project/model.py');
const notebook = new Uri('file', '/project/experiment.ipynb');
const cell = new Uri('vscode-notebook-cell', '/project/experiment.ipynb#1');
const document = { uri: notebook, getCells: () => [{ document: { uri: cell } }] };
let trusted = true, enabled = true;
const fake = {
    Uri, Range: class {}, CodeLens: class { constructor(range, command) { this.command = command; } },
    window: { activeTextEditor: { document: { uri: script } }, activeNotebookEditor: { notebook: document } },
    workspace: { notebookDocuments: [document], get isTrusted() { return trusted; }, getConfiguration: () => ({ get: () => enabled }) },
};
const originalLoad = Module._load;
Module._load = function (id, ...args) { return id === 'vscode' ? fake : originalLoad.call(this, id, ...args); };
const { sourceUri, inspectionLenses } = require('../out/workbench');
const { renderDashboard } = require('../out/dashboard');
const { parseJson } = require('../out/json');
Module._load = originalLoad;

test('editor actions target the selected script or owning notebook, never another visible editor', () => {
    assert.equal(sourceUri(), script, 'An open notebook cannot override the active Python file');
    assert.equal(sourceUri(cell), notebook, 'Cell editor context maps to its saved notebook');
    assert.equal(sourceUri({ notebookEditor: { notebook: document } }), notebook, 'Notebook toolbar context wins');
    assert.equal(sourceUri({ notebook: document }), notebook);
    fake.window.activeTextEditor = { document: { uri: cell } };
    assert.equal(sourceUri(), notebook);
    assert.equal(sourceUri(new Uri('vscode-notebook-cell', '/unknown#1')), undefined, 'Unowned cells are not guessed');
    assert.equal(sourceUri(new Uri('untitled', 'Untitled-1')), undefined, 'Unsaved sources cannot fall back to a different notebook');
    fake.window.activeTextEditor = { document: { uri: script } };
});

test('Python shortcuts are explicit commands and respect trust and the opt-out', () => {
    assert.deepEqual(inspectionLenses({ uri: script }).map(lens => lens.command.command), ['apizr.inspect', 'apizr.openDashboard']);
    trusted = false; assert.deepEqual(inspectionLenses({ uri: script }), []); trusted = true;
    enabled = false; assert.deepEqual(inspectionLenses({ uri: script }), []); enabled = true;
});

test('dashboard renders local canonical history without scripts, HTML injection or numeric rounding', () => {
    const history = parseJson('{"total":1,"matched":1,"runs":[{"run_digest":"abcdef123456","status":"success","source":{"identity":{"reference":"<script>model.py</script>"}},"capture":{"mode":"jupyter_cell"},"started_at":null,"parameters":[{"name":"size","value":9223372036854775807}],"recorded_metrics":[{"name":"<img src=x onerror=alert(1)>","value":1.2300e-7}]}]}');
    const html = renderDashboard(history, undefined, '<project>');
    assert.match(html, /9223372036854775807/);
    assert.match(html, /1\.2300e-7/);
    assert.match(html, /Jupyter/);
    assert.match(html, /&lt;script&gt;model.py&lt;\/script&gt;/);
    assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
    assert.doesNotMatch(html, /<script|<img|https?:\/\//);
    assert.match(html, /default-src 'none'/);
    assert.match(html, /1 validated Runs/);
    assert.match(renderDashboard(), /Select engine/);
    assert.match(renderDashboard({ total: 0, matched: 0, runs: [] }), /No recorded Runs/);
});
