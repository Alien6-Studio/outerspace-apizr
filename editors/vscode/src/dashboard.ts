import * as vscode from "vscode";
import { Json, object } from "./engine";
import { numberToken, stringify } from "./json";

type Value = { [key: string]: Json };
const escape = (value: unknown): string => String(value ?? "Unknown").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]!));
const text = (value: Json | undefined): string => escape(value === undefined || value === null ? "Unknown" : typeof value === "string" ? value : stringify(value));
function link(command: string, label: string, args: Json[] = []): string {
    return `<a class="button" href="command:apizr.${command}?${encodeURIComponent(stringify(args))}">${escape(label)}</a>`;
}
export function sourceReference(source: Json | undefined): string {
    const identity = object(source) && object(source.identity) ? source.identity : source;
    return object(identity) && typeof identity.reference === "string" ? identity.reference : "Unknown source";
}
export function captureLabel(capture: Json | undefined): string {
    const mode = object(capture) ? capture.mode : undefined;
    return mode === "jupyter_cell" ? "Jupyter" : mode === "sdk_session" ? "SDK" : mode === "decorated_call" ? "Decorated call" : mode === "cli_run" ? "CLI" : "Unknown";
}
function values(items: Json | undefined): string {
    if (!Array.isArray(items) || !items.length) { return "<span class=muted>None recorded</span>"; }
    return items.filter(object).map(item => `<div><strong>${text(item.name)}</strong>: <code>${numberToken(item, "value") ? escape(numberToken(item, "value")) : text(item.value)}</code>${item.unit ? ` ${text(item.unit)}` : ""}</div>`).join("");
}
export function renderDashboard(history?: Value, record?: Value, project = ""): string {
    const runs = Array.isArray(history?.runs) ? history.runs.filter(object) : [];
    const rows = runs.map(run => `<tr><td>${link("showTrackedRun", String(run.run_digest).slice(0, 12), [run.run_digest])}<br><span class=muted>${text(run.started_at)}</span></td><td>${text(run.status)}<br><span class=muted>${escape(captureLabel(run.capture))}</span></td><td>${escape(sourceReference(run.source))}</td><td>${Array.isArray(run.parameters) ? values(run.parameters) : "Open Run for parameters"}</td><td>${Array.isArray(run.recorded_metrics) ? values(run.recorded_metrics) : `${text(run.metrics)} recorded`}</td></tr>`).join("");
    const run = object(record?.run) ? record.run : undefined;
    const details = run ? `<section><h2>Selected Run <code>${text(record?.run_digest)}</code></h2><p>${text(run.status)} · ${escape(captureLabel(run.capture))} · ${escape(sourceReference(run.subject))}</p><div class=columns><div><h3>Parameters</h3>${values(run.effective_parameters)}<h3>Call parameters</h3>${values(run.call_parameters)}</div><div><h3>Metrics</h3>${values(run.metrics)}</div></div><p>${link("showRun", "Open complete JSON", [record!.run_digest])} ${link("openSource", "Open recorded source")}</p></section>` : "";
    return `<!DOCTYPE html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline';"><title>Apizr — Experiment tracking</title><style>
body{font:var(--vscode-font-size)/1.6 var(--vscode-font-family);color:var(--vscode-editor-foreground);background:var(--vscode-editor-background);max-width:1200px;margin:32px auto;padding:0 24px}h1{font-size:26px;margin:0}h2{font-size:18px}h3{font-size:14px}a{color:var(--vscode-textLink-foreground)}.muted{color:var(--vscode-descriptionForeground);font-size:12px}.button{display:inline-block;padding:5px 10px;margin:2px 5px 2px 0;border:1px solid var(--vscode-button-border,var(--vscode-panel-border));border-radius:3px;text-decoration:none}a:hover{background:var(--vscode-list-hoverBackground)}a:focus-visible{outline:1px solid var(--vscode-focusBorder)}section{margin:24px 0;padding:16px;border:1px solid var(--vscode-panel-border);border-radius:4px}.columns{display:flex;flex-wrap:wrap;gap:40px}.columns>div{flex:1;min-width:200px}table{border-collapse:collapse;width:100%;font-size:13px}th{text-align:left;color:var(--vscode-descriptionForeground)}td,th{padding:10px 12px;border-bottom:1px solid var(--vscode-panel-border);vertical-align:top}td{overflow-wrap:anywhere}code{font-family:var(--vscode-editor-font-family);overflow-wrap:anywhere}.table{overflow-x:auto}header p{margin:4px 0 16px}strong{font-weight:600}
</style></head><body><header><h1>Experiment tracking</h1><p class=muted>Apizr${project ? ` · ${escape(project)}` : ""} · Local experiment evidence</p><nav aria-label="Experiment actions">${link("refreshRuns", "Refresh history")} ${link("inspect", "Inspect saved source")} ${link("compareRuns", "Compare two Runs")}</nav></header>
${history ? `<section><h2>History</h2><p>${text(history.total)} validated Runs · ${text(history.matched)} matched · ${runs.length} shown (up to 20)</p>${runs.length ? `<div class=table><table><thead><tr><th scope=col>Run / started</th><th scope=col>Status / capture</th><th scope=col>Source</th><th scope=col>Parameters</th><th scope=col>Metrics</th></tr></thead><tbody>${rows}</tbody></table></div>` : "<p>No recorded Runs in this store. Run your instrumented Python code or notebook, then refresh history.</p>"}</section>` : `<section><h2>Connect your project</h2><p>Open a trusted folder with <code>apizr.toml</code>, select your installed engine and configure an operator policy. Then refresh history to see CLI, SDK and Jupyter Runs together.</p>${link("selectEngine", "Select engine")} ${link("checkEngine", "Check engine")} ${link("openSettings", "Project settings")}</section>`}
${details}<p class=muted>History is validated by the Apizr engine. After your first refresh, newly saved Runs update this view. Inspection reads saved source; it does not execute Python code. Usage telemetry is separate from experiment tracking.</p></body></html>`;
}

/** Script-free, local projection of the engine's canonical history and records. */
export class Dashboard implements vscode.Disposable {
    private panel?: vscode.WebviewPanel;
    private history?: Value;
    private record?: Value;
    private project = "";
    constructor(private readonly icon: vscode.Uri) {}
    show(): void {
        if (!this.panel) {
            this.panel = vscode.window.createWebviewPanel("apizr.dashboard", "Apizr — Experiments", vscode.ViewColumn.Active, {
                enableScripts: false, localResourceRoots: [],
                enableCommandUris: ["apizr.refreshRuns", "apizr.inspect", "apizr.compareRuns", "apizr.showTrackedRun", "apizr.showRun", "apizr.openSource", "apizr.selectEngine", "apizr.checkEngine", "apizr.openSettings"],
            });
            this.panel.iconPath = this.icon;
            this.panel.onDidDispose(() => { this.panel = undefined; });
        }
        this.panel.reveal(); this.render();
    }
    update(history: Value | undefined, project: string): void {
        if (project !== this.project || !history) { this.record = undefined; }
        this.history = history; this.project = project; this.render();
    }
    select(record?: Value): void { this.record = record; this.render(); }
    clear(): void { this.history = undefined; this.record = undefined; this.project = ""; this.render(); }
    private render(): void { if (this.panel) { this.panel.webview.html = renderDashboard(this.history, this.record, this.project); } }
    dispose(): void { this.panel?.dispose(); }
}
